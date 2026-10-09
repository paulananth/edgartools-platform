//! The Python binding (`--features python`, built by maturin). Python reaches
//! the engine only through `edgar_warehouse/rules/source_engine.py`.

use pyo3::create_exception;
use pyo3::exceptions::PyException;
use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList, PyString};
use pyo3::IntoPyObjectExt;

use crate::{Engine, Lookups, Raw, Rejected, Step, Steps, Val};

create_exception!(source_contract, SourceRejected, PyException);

fn rejected(error: Rejected) -> PyErr {
    SourceRejected::new_err((error.code, error.detail))
}

fn indexed_sets(engine: &Engine, lookups: Option<&Bound<'_, PyDict>>) -> PyResult<Lookups> {
    let mut sets = Lookups::new();
    let Some(lookups) = lookups else { return Ok(sets) };
    let mut aggregate = 0usize;
    for (name, values) in lookups.iter() {
        let name: String = name.extract()?;
        let bounds = crate::lookup_sets::input_bounds(&engine.read, &name).map_err(rejected)?;
        let mut chosen = std::collections::BTreeSet::new();
        let mut count = 0usize;
        let mut bytes = 0usize;
        for item in values.try_iter()? {
            let item = item?;
            count = count.checked_add(1).ok_or_else(|| rejected(Rejected::new("limit_exceeded", "lookup count overflow")))?;
            if bounds.is_some_and(|(maximum,_,_)| count > maximum) {
                return Err(rejected(Rejected::new("limit_exceeded", "lookup raw values exceed max_values")));
            }
            let text = item.downcast::<PyString>()?.to_str()?;
            if let Some((_,maximum,max_value)) = bounds {
                if text.len() > max_value { return Err(rejected(Rejected::new("limit_exceeded", "lookup key exceeds max_value_bytes"))); }
                bytes = bytes.checked_add(text.len()).ok_or_else(|| rejected(Rejected::new("limit_exceeded", "lookup byte count overflow")))?;
                aggregate = aggregate.checked_add(text.len()).ok_or_else(|| rejected(Rejected::new("limit_exceeded", "lookup byte count overflow")))?;
                if bytes > maximum || aggregate > 64 * 1024 * 1024 {
                    return Err(rejected(Rejected::new("limit_exceeded", "lookup raw values exceed byte budget")));
                }
            }
            chosen.insert(text.to_owned());
        }
        sets.insert(name, chosen);
    }
    Ok(sets)
}

fn to_py(py: Python<'_>, value: &Val) -> PyResult<PyObject> {
    match value {
        Val::Null => Ok(py.None()),
        Val::Int(i) => i.into_py_any(py),
        Val::UInt(i) => i.into_py_any(py),
        Val::List(items) => {
            let list = PyList::empty(py);
            for item in items { list.append(to_py(py, item)?)?; }
            list.into_py_any(py)
        }
        Val::Map(values) => {
            let dict = PyDict::new(py);
            for (key, value) in values { dict.set_item(key, to_py(py, value)?)?; }
            dict.into_py_any(py)
        }
        Val::Bool(b) => b.into_py_any(py),
        Val::Float(f) => f.into_py_any(py),
        Val::Str(s) => s.into_py_any(py),
    }
}

fn from_py(value: &Bound<'_, PyAny>) -> PyResult<Val> {
    if value.is_none() {
        Ok(Val::Null)
    } else if let Ok(flag) = value.downcast::<pyo3::types::PyBool>() {
        Ok(Val::Str(flag.is_true().to_string()))
    } else if let Ok(text) = value.extract::<String>() {
        Ok(Val::Str(text))
    } else if let Ok(int) = value.extract::<i64>() {
        Ok(Val::Int(int))
    } else {
        Ok(Val::Float(value.extract::<f64>()?))
    }
}

fn raw_to_py(py: Python<'_>, raw: &Raw) -> PyResult<PyObject> {
    match raw {
        Raw::Null => Ok(py.None()),
        Raw::Text(text) => text.into_py_any(py),
        Raw::List(items) => {
            let list = PyList::empty(py);
            for item in items {
                list.append(raw_to_py(py, item)?)?;
            }
            list.into_py_any(py)
        }
        Raw::Map(map) => {
            let dict = PyDict::new(py);
            for (key, value) in map {
                dict.set_item(key, raw_to_py(py, value)?)?;
            }
            dict.into_py_any(py)
        }
    }
}

/// A Python function as a step: it gets one value and returns one.
fn step(function: Py<PyAny>) -> Step {
    Box::new(move |value: &Val| {
        Python::with_gil(|py| {
            let out = function.call1(py, (to_py(py, value)?,))?;
            from_py(out.bind(py))
        })
        .map_err(|error| error.to_string())
    })
}

#[pyclass(name = "Engine", module = "source_contract", frozen)]
struct PyEngine {
    inner: Engine,
}

#[pymethods]
impl PyEngine {
    #[new]
    fn new(contract: &str, steps: &Bound<'_, PyDict>) -> PyResult<Self> {
        let mut registered = Steps::new();
        for (name, function) in steps.iter() {
            registered.insert(name.extract()?, step(function.unbind()));
        }
        Engine::from_yaml(contract, registered).map(|inner| Self { inner }).map_err(rejected)
    }

    fn validate_context(&self, context: &str) -> PyResult<()> {
        let values = crate::context::from_json(context).map_err(rejected)?;
        self.inner.validate_context(&values).map_err(rejected)
    }

    #[pyo3(signature = (stream, wrapper, on_reading, *, max_bytes, max_record, max_records, max_depth=64, min_integer=i64::MIN, record_encoding="native", context="{}", ordinal_context=None, lookups=None))]
    fn scan_json_array(&self, py: Python<'_>, stream: Py<PyAny>, wrapper: String, on_reading: Py<PyAny>,
                       max_bytes: usize, max_record: usize, max_records: usize, max_depth: usize,
                       min_integer: i64, record_encoding: &str, context: &str, ordinal_context: Option<String>, lookups: Option<&Bound<'_, PyDict>>) -> PyResult<(usize, usize)> {
        let record_encoding = match record_encoding {
            "native" => crate::json_sequence::RecordEncoding::Native,
            "python" => crate::json_sequence::RecordEncoding::Python,
            _ => return Err(rejected(crate::Rejected::new("contract", "record_encoding is native or python"))),
        };
        let sets = indexed_sets(&self.inner, lookups)?;
        let projection = self.inner.prepare_json_projection(&sets).map_err(rejected)?;
        let mut values = crate::context::from_json(context).map_err(rejected)?;
        if let Some(name) = &ordinal_context {
            if values.contains_key(name) {
                return Err(rejected(crate::Rejected::new("invalid_context", "stream ordinal context is generated, never supplied")));
            }
            values.insert(name.clone(), Val::Int(1));
        }
        self.inner.validate_context(&values).map_err(rejected)?;
        let limits = crate::json_sequence::Limits { max_bytes, max_record, max_records, max_depth, min_integer, record_encoding };
        let result = py.allow_threads(|| crate::json_sequence::scan(PythonReader(stream), &wrapper, limits, |record, ordinal| {
            if let Some(name) = &ordinal_context {
                let position = i64::try_from(ordinal).ok().and_then(|n| n.checked_add(1))
                    .ok_or_else(|| crate::Rejected::new("limit_exceeded", "stream ordinal exceeds signed integer range"))?;
                values.insert(name.clone(), Val::Int(position));
            }
            let reading = projection.read_json_value(record, &values)?;
            Python::with_gil(|py| on_reading.call1(py, (reading_to_py(py, &reading)?, ordinal)).map(|_| ()))
                .map_err(|error| crate::Rejected::new("stream_consumer", error))
        })).map_err(rejected)?;
        Ok((result.records, result.bytes))
    }

    #[pyo3(signature = (data, lookups, context="{}"))]
    fn read(&self, py: Python<'_>, data: &[u8], lookups: &Bound<'_, PyDict>, context: &str) -> PyResult<PyObject> {
        let sets = indexed_sets(&self.inner, Some(lookups))?;
        let context = crate::context::from_json(context).map_err(rejected)?;
        // Other Python threads run while the engine reads; a step takes the
        // interpreter back for its own call.
        let reading = py.allow_threads(|| self.inner.read_with_context(data, &sets, &context)).map_err(rejected)?;
        reading_to_py(py, &reading)
    }

    #[pyo3(signature = (stream, envelope, header_engine, on_reading, *, max_bytes, max_record, max_records, max_depth=64, max_header=None, context="{}", ordinal_context=None))]
    fn scan_xml_records(&self, py: Python<'_>, stream: Py<PyAny>, envelope: &str, header_engine: &PyEngine,
                        on_reading: Py<PyAny>, max_bytes: usize, max_record: usize, max_records: usize,
                        max_depth: usize, max_header: Option<usize>, context: &str, ordinal_context: Option<String>) -> PyResult<(usize, usize)> {
        if envelope.len() > 4096 { return Err(rejected(Rejected::new("contract", "XML envelope exceeds bound"))); }
        let envelope: crate::xml_sequence::Envelope = serde_json::from_str(envelope)
            .map_err(|error| rejected(Rejected::new("contract", error)))?;
        self.inner.validate_json_projection().map_err(rejected)?;
        header_engine.inner.validate_json_projection().map_err(rejected)?;
        let mut values = crate::context::from_json(context).map_err(rejected)?;
        if let Some(name) = &ordinal_context {
            if values.contains_key(name) { return Err(rejected(Rejected::new("invalid_context", "stream ordinal context is generated, never supplied"))); }
            values.insert(name.clone(), Val::Int(1));
        }
        self.inner.validate_context(&values).map_err(rejected)?;
        header_engine.inner.validate_context(&values).map_err(rejected)?;
        let header_context = values.clone();
        let header = &header_engine.inner;
        let limits = crate::xml_sequence::Limits { max_bytes, max_record, max_header: max_header.unwrap_or(max_record), max_records, max_depth };
        let result = py.allow_threads(|| crate::xml_sequence::scan(PythonReader(stream), &envelope, limits, |value| {
            let reading = header.read_json_value(value, &Lookups::new(), &header_context)?;
            if !reading.deferred.is_empty() { return Err(Rejected::new("xml_header", "XML header assertions must pass, not defer")); }
            Ok(())
        }, |record, ordinal| {
            if let Some(name) = &ordinal_context {
                let position = i64::try_from(ordinal).ok().and_then(|n| n.checked_add(1))
                    .ok_or_else(|| Rejected::new("limit_exceeded", "stream ordinal exceeds signed integer range"))?;
                values.insert(name.clone(), Val::Int(position));
            }
            let reading = self.inner.read_json_value(record, &Lookups::new(), &values)?;
            Python::with_gil(|py| on_reading.call1(py, (reading_to_py(py, &reading)?, ordinal)).map(|_| ()))
                .map_err(|error| Rejected::new("stream_consumer", error))
        })).map_err(rejected)?;
        Ok((result.records, result.bytes))
    }
}

fn reading_to_py(py: Python<'_>, reading: &crate::Reading) -> PyResult<PyObject> {
    let tables = PyDict::new(py);
    for (name, rows) in &reading.tables {
        let list = PyList::empty(py);
        for row in rows {
            let dict = PyDict::new(py);
            for (column, value) in row {
                dict.set_item(column, to_py(py, value)?)?;
            }
            list.append(dict)?;
        }
        tables.set_item(name, list)?;
    }
    let deferred = PyList::empty(py);
    for record in &reading.deferred {
        let dict = PyDict::new(py);
        dict.set_item("table", &record.table)?;
        dict.set_item("ordinal", record.ordinal)?;
        dict.set_item("reason", &record.reason)?;
        dict.set_item("raw", raw_to_py(py, &record.raw)?)?;
        deferred.append(dict)?;
    }
    let out = PyDict::new(py);
    out.set_item("tables", tables)?;
    out.set_item("deferred", deferred)?;
    out.into_py_any(py)
}

#[pymodule]
fn source_contract(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<PyEngine>()?;
    m.add("SourceRejected", m.py().get_type::<SourceRejected>())?;
    m.add_function(wrap_pyfunction!(scan_json_array, m)?)?;
    Ok(())
}

struct PythonReader(Py<PyAny>);

impl std::io::Read for PythonReader {
    fn read(&mut self, buffer: &mut [u8]) -> std::io::Result<usize> {
        Python::with_gil(|py| {
            let result = self.0.bind(py).call_method1("read", (buffer.len(),))?;
            let bytes = result.downcast::<pyo3::types::PyBytes>()?.as_bytes();
            if bytes.len() > buffer.len() { return Err(pyo3::exceptions::PyValueError::new_err("reader returned more bytes than requested")); }
            buffer[..bytes.len()].copy_from_slice(bytes);
            Ok(bytes.len())
        }).map_err(|error: PyErr| std::io::Error::other(error.to_string()))
    }
}

fn json_to_py(py: Python<'_>, value: &serde_json::Value) -> PyResult<PyObject> {
    match value {
        serde_json::Value::Null => Ok(py.None()),
        serde_json::Value::Bool(value) => value.into_py_any(py),
        serde_json::Value::String(value) => value.into_py_any(py),
        serde_json::Value::Number(value) => match value.as_i64() {
            Some(value) => value.into_py_any(py),
            None => value.as_f64().unwrap().into_py_any(py),
        },
        serde_json::Value::Array(values) => {
            let list = PyList::empty(py);
            for value in values { list.append(json_to_py(py, value)?)?; }
            list.into_py_any(py)
        },
        serde_json::Value::Object(values) => {
            let dict = PyDict::new(py);
            for (key, value) in values { dict.set_item(key, json_to_py(py, value)?)?; }
            dict.into_py_any(py)
        },
    }
}

#[pyfunction]
#[pyo3(signature = (stream, wrapper, on_record, *, max_bytes, max_record, max_records, max_depth=64, min_integer=i64::MIN, record_encoding="native"))]
fn scan_json_array(py: Python<'_>, stream: Py<PyAny>, wrapper: String, on_record: Py<PyAny>,
                   max_bytes: usize, max_record: usize, max_records: usize, max_depth: usize, min_integer: i64, record_encoding: &str) -> PyResult<(usize, usize)> {
    let record_encoding = match record_encoding {
        "native" => crate::json_sequence::RecordEncoding::Native,
        "python" => crate::json_sequence::RecordEncoding::Python,
        _ => return Err(rejected(crate::Rejected::new("contract", "record_encoding is native or python"))),
    };
    let limits = crate::json_sequence::Limits { max_bytes, max_record, max_records, max_depth, min_integer, record_encoding };
    let result = py.allow_threads(|| crate::json_sequence::scan(PythonReader(stream), &wrapper, limits, |record, ordinal| {
        Python::with_gil(|py| on_record.call1(py, (json_to_py(py, &record)?, ordinal)).map(|_| ()))
            .map_err(|error| crate::Rejected::new("stream_consumer", error))
    })).map_err(rejected)?;
    Ok((result.records, result.bytes))
}
