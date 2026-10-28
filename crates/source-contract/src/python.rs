//! The Python binding (`--features python`, built by maturin). Python reaches
//! the engine only through `edgar_warehouse/rules/source_engine.py`.

use pyo3::create_exception;
use pyo3::exceptions::PyException;
use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use pyo3::types::{PyBytes, PyDict, PyList, PyString};
use pyo3::IntoPyObjectExt;

use crate::{Engine, Lookups, Raw, Rejected, Step, Steps, Val};

create_exception!(source_contract, SourceRejected, PyException);

fn rejected(error: Rejected) -> PyErr {
    SourceRejected::new_err((error.code, error.detail))
}

fn indexed_sets(engine: &Engine, lookups: Option<&Bound<'_, PyDict>>) -> PyResult<Lookups> {
    use crate::lookup_sets::{LookupSet, MAX_AGGREGATE_BYTES};
    let limit = |detail: &str| rejected(Rejected::new("limit_exceeded", detail));
    let mut sets = Lookups::new();
    let Some(lookups) = lookups else { return Ok(sets) };
    let mut aggregate = 0usize;
    for (name, values) in lookups.iter() {
        let name: String = name.extract()?;
        let bounds = crate::lookup_sets::input_bounds(&engine.read, &name).map_err(rejected)?;
        let pairs = bounds.is_some_and(|(_, _, _, pairs)| pairs);
        let mut members = std::collections::BTreeSet::new();
        let mut keyed = std::collections::BTreeSet::new();
        let mut count = 0usize;
        let mut bytes = 0usize;
        for item in values.try_iter()? {
            let item = item?;
            count = count.checked_add(1).ok_or_else(|| limit("lookup count overflow"))?;
            if bounds.is_some_and(|(maximum, _, _, _)| count > maximum) {
                return Err(limit("lookup raw values exceed max_values"));
            }
            // A pair set's item is a key and its value (a tuple); a membership set's, one text.
            let (key, value): (String, Option<String>) = if pairs {
                let (key, value): (String, String) = item.extract()
                    .map_err(|_| rejected(Rejected::new("invalid_lookup", "a pair set item is a tuple of a key and a value, both text")))?;
                (key, Some(value))
            } else {
                (item.downcast::<PyString>()?.to_str()?.to_owned(), None)
            };
            if let Some((_, maximum, max_value, _)) = bounds {
                for text in std::iter::once(&key).chain(value.as_ref()) {
                    if text.len() > max_value { return Err(limit("a lookup key or value exceeds max_value_bytes")); }
                    bytes = bytes.checked_add(text.len()).ok_or_else(|| limit("lookup byte count overflow"))?;
                    aggregate = aggregate.checked_add(text.len()).ok_or_else(|| limit("lookup byte count overflow"))?;
                }
                if bytes > maximum || aggregate > MAX_AGGREGATE_BYTES {
                    return Err(limit("lookup raw values exceed byte budget"));
                }
            }
            match value {
                Some(value) => { keyed.insert((key, value)); }
                None => { members.insert(key); }
            }
        }
        sets.insert(name, if pairs { LookupSet::Pairs(keyed) } else { LookupSet::Members(members) });
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
    fn scan_json_array(&self, py: Python<'_>, stream: Py<PyAny>, wrapper: Option<String>, on_reading: Py<PyAny>,
                       max_bytes: usize, max_record: usize, max_records: usize, max_depth: usize,
                       min_integer: i64, record_encoding: &str, context: &str, ordinal_context: Option<String>, lookups: Option<&Bound<'_, PyDict>>) -> PyResult<(usize, usize)> {
        let record_encoding = match record_encoding {
            "native" => crate::json_sequence::RecordEncoding::Native,
            "python" => crate::json_sequence::RecordEncoding::Python,
            _ => return Err(rejected(crate::Rejected::new("contract", "record_encoding is native or python"))),
        };
        let sets = indexed_sets(&self.inner, lookups)?;
        let projection = self.inner.prepare_json_projection(&sets).map_err(rejected)?;
        let mut values = stream_context(context, &ordinal_context)?;
        self.inner.validate_context(&values).map_err(rejected)?;
        let limits = crate::json_sequence::Limits { max_bytes, max_record, max_records, max_depth, min_integer, record_encoding };
        let result = py.allow_threads(|| crate::json_sequence::scan(PythonReader(stream), wrapper.as_deref(), limits, |record, ordinal| {
            emit(&mut values, &ordinal_context, ordinal, &on_reading, |values| projection.read_json_value(record, values))
        })).map_err(rejected)?;
        Ok((result.records, result.bytes))
    }

    #[pyo3(signature = (stream, format, encoding, on_reading, *, max_bytes, max_record, max_records, context="{}", ordinal_context=None, lookups=None))]
    fn scan_delimited(&self, py: Python<'_>, stream: Py<PyAny>, format: &str, encoding: &str, on_reading: Py<PyAny>,
                      max_bytes: usize, max_record: usize, max_records: usize, context: &str,
                      ordinal_context: Option<String>, lookups: Option<&Bound<'_, PyDict>>) -> PyResult<(usize, usize)> {
        let format = crate::delimited_sequence::Format::named(format).map_err(rejected)?;
        let sets = indexed_sets(&self.inner, lookups)?;
        let projection = self.inner.prepare_json_projection(&sets).map_err(rejected)?;
        let mut values = stream_context(context, &ordinal_context)?;
        self.inner.validate_context(&values).map_err(rejected)?;
        let limits = crate::delimited_sequence::Limits { max_bytes, max_record, max_records };
        let encoding = encoding.to_string();
        let result = py.allow_threads(|| crate::delimited_sequence::scan(PythonReader(stream), format, &encoding, limits, |record, ordinal| {
            emit(&mut values, &ordinal_context, ordinal, &on_reading, |values| projection.read_json_value(record, values))
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
        let mut values = stream_context(context, &ordinal_context)?;
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
            emit(&mut values, &ordinal_context, ordinal, &on_reading, |values| self.inner.read_json_value(record, &Lookups::new(), values))
        })).map_err(rejected)?;
        Ok((result.records, result.bytes))
    }
}

/// The caller's facts for a stream, with the generated ordinal seeded at 1.
fn stream_context(context: &str, ordinal_context: &Option<String>) -> PyResult<crate::Row> {
    let mut values = crate::context::from_json(context).map_err(rejected)?;
    if let Some(name) = ordinal_context {
        if values.contains_key(name) {
            return Err(rejected(Rejected::new("invalid_context", "stream ordinal context is generated, never supplied")));
        }
        values.insert(name.clone(), Val::Int(1));
    }
    Ok(values)
}

/// Stamps the record's one-based ordinal, projects it and hands the reading to Python.
fn emit(values: &mut crate::Row, ordinal_context: &Option<String>, ordinal: usize, on_reading: &Py<PyAny>,
        project: impl FnOnce(&crate::Row) -> Result<crate::Reading, Rejected>) -> Result<(), Rejected> {
    if let Some(name) = ordinal_context {
        let position = i64::try_from(ordinal).ok().and_then(|n| n.checked_add(1))
            .ok_or_else(|| Rejected::new("limit_exceeded", "stream ordinal exceeds signed integer range"))?;
        values.insert(name.clone(), Val::Int(position));
    }
    let reading = project(values)?;
    Python::with_gil(|py| on_reading.call1(py, (reading_to_py(py, &reading)?, ordinal)).map(|_| ()))
        .map_err(|error| Rejected::new("stream_consumer", error))
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
    m.add_class::<PyReduction>()?;
    m.add_function(wrap_pyfunction!(rank_claims, m)?)?;
    m.add_function(wrap_pyfunction!(crate::combination::combine_tables, m)?)?;
    m.add_function(wrap_pyfunction!(replay_identity, m)?)?;
    m.add_function(wrap_pyfunction!(replay_record_decisions, m)?)?;
    m.add_function(wrap_pyfunction!(prepare_master_records, m)?)?;
    m.add_function(wrap_pyfunction!(compare_matching_values, m)?)?;
    m.add_function(wrap_pyfunction!(apply_record_rules, m)?)?;
    m.add_function(wrap_pyfunction!(plan_record_matches, m)?)?;
    m.add_function(wrap_pyfunction!(link_matching_records, m)?)?;
    m.add_function(wrap_pyfunction!(compare_record_pairs, m)?)?;
    m.add_function(wrap_pyfunction!(prepare_record_history, m)?)?;
    m.add_function(wrap_pyfunction!(plan_affected_records, m)?)?;
    m.add_function(wrap_pyfunction!(prepare_record_lookups, m)?)?;
    m.add_function(wrap_pyfunction!(prepare_scope_lookups, m)?)?;
    m.add_function(wrap_pyfunction!(resolve_record_bindings, m)?)?;
    m.add_function(wrap_pyfunction!(prepare_current_records, m)?)?;
    m.add_function(wrap_pyfunction!(identify_profile, m)?)?;
    m.add_function(wrap_pyfunction!(choose_field_values, m)?)?;
    m.add_function(wrap_pyfunction!(describe_field_rules, m)?)?;
    m.add_function(wrap_pyfunction!(prepare_relationships, m)?)?;
    m.add_function(wrap_pyfunction!(prepare_relationship_types, m)?)?;
    m.add_function(wrap_pyfunction!(prepare_relationship_periods, m)?)?;
    m.add("SourceRejected", m.py().get_type::<SourceRejected>())?;
    m.add_function(wrap_pyfunction!(scan_json_array, m)?)?;
    m.add_function(wrap_pyfunction!(postgres_jsonb_text, m)?)?;
    m.add_function(wrap_pyfunction!(postgres_jsonb_object, m)?)?;
    m.add_function(wrap_pyfunction!(postgres_jsonb_object_bytes, m)?)?;
    Ok(())
}

#[pyfunction]
fn postgres_jsonb_text(py: Python<'_>, raw: &str) -> PyResult<String> {
    py.allow_threads(|| crate::postgres_jsonb::text(raw)).map_err(PyValueError::new_err)
}

#[pyfunction]
#[pyo3(signature = (fields, *, canonical_inputs=false))]
fn postgres_jsonb_object(py: Python<'_>, fields: std::collections::HashMap<String, String>, canonical_inputs: bool) -> PyResult<String> {
    py.allow_threads(|| crate::postgres_jsonb::object(fields, canonical_inputs)).map_err(PyValueError::new_err)
}

#[pyfunction]
#[pyo3(signature = (fields, *, canonical_inputs=false))]
fn postgres_jsonb_object_bytes(py: Python<'_>, fields: std::collections::HashMap<String, String>, canonical_inputs: bool) -> PyResult<Py<PyBytes>> {
    let raw = py.allow_threads(|| crate::postgres_jsonb::object(fields, canonical_inputs)).map_err(PyValueError::new_err)?;
    Ok(PyBytes::new(py, raw.as_bytes()).unbind())
}

// Only selected text columns cross this boundary. Input history is never
// retained; bounded conversion batches release the GIL for native accumulation.
#[pyclass(name = "Reduction", module = "source_contract")]
struct PyReduction {
    inner: crate::reduction::Reduction,
}

fn reduction_text(row: &Bound<'_, PyDict>, column: &str) -> PyResult<String> {
    let error = || PyValueError::new_err(format!("Reduction column {column} must contain exact text"));
    let value = row.get_item(column)?.ok_or_else(error)?;
    let text = value.downcast::<PyString>().map_err(|_| error())?;
    Ok(text.to_str()?.to_owned())
}

#[pymethods]
impl PyReduction {
    #[new]
    fn new(plan: &str) -> PyResult<Self> {
        Ok(Self { inner: crate::reduction::Reduction::new(plan).map_err(PyValueError::new_err)? })
    }

    fn push(&mut self, py: Python<'_>, group: &str, rows: &Bound<'_, PyList>) -> PyResult<()> {
        let result = (|| {
            let spec = self.inner.spec(group).map_err(PyValueError::new_err)?.clone();
            let mut input = rows.iter();
            loop {
                let mut batch = Vec::with_capacity(1024);
                let mut fault = None;
                for _ in 0..1024 {
                    let Some(row) = input.next() else { break; };
                    let converted = (|| {
                        let row = row.downcast::<PyDict>()
                            .map_err(|_| PyValueError::new_err("Reduction row must be an object"))?;
                        let key = spec.keys.iter().map(|column| reduction_text(row, column))
                            .collect::<PyResult<Vec<_>>>()?;
                        // `most`: a null value is a row that files none; a missing column is refused.
                        let member = match &spec.member {
                            Some(column) if spec.mode == crate::reduction::Mode::Most
                                && row.get_item(column)?.is_some_and(|value| value.is_none()) => None,
                            Some(column) => Some(reduction_text(row, column)?),
                            None => None,
                        };
                        let last = if let Some(column) = &spec.last {
                            if row.get_item(column)?.is_some_and(|value| value.is_none()) && spec.last_null.is_some() {
                                spec.last_null.clone()
                            } else { Some(reduction_text(row, column)?) }
                        } else { None };
                        Ok(crate::reduction::Row { key, member, last })
                    })();
                    match converted {
                        Ok(row) => batch.push(row),
                        Err(error) => { fault = Some(error); break; }
                    }
                }
                let empty = batch.is_empty();
                // Process the valid prefix first to preserve state-budget error
                // precedence over a later malformed row in the same batch.
                py.allow_threads(|| self.inner.push(group, batch)).map_err(PyValueError::new_err)?;
                if let Some(error) = fault { return Err(error); }
                if empty { break; }
            }
            Ok(())
        })();
        if result.is_err() { self.inner.invalidate(); }
        result
    }

    fn finish(&mut self, py: Python<'_>) -> PyResult<PyObject> {
        let tables = py.allow_threads(|| self.inner.finish()).map_err(PyValueError::new_err)?;
        json_to_py(py, &tables)
    }
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
fn scan_json_array(py: Python<'_>, stream: Py<PyAny>, wrapper: Option<String>, on_record: Py<PyAny>,
                   max_bytes: usize, max_record: usize, max_records: usize, max_depth: usize, min_integer: i64, record_encoding: &str) -> PyResult<(usize, usize)> {
    let record_encoding = match record_encoding {
        "native" => crate::json_sequence::RecordEncoding::Native,
        "python" => crate::json_sequence::RecordEncoding::Python,
        _ => return Err(rejected(crate::Rejected::new("contract", "record_encoding is native or python"))),
    };
    let limits = crate::json_sequence::Limits { max_bytes, max_record, max_records, max_depth, min_integer, record_encoding };
    let result = py.allow_threads(|| crate::json_sequence::scan(PythonReader(stream), wrapper.as_deref(), limits, |record, ordinal| {
        Python::with_gil(|py| on_record.call1(py, (json_to_py(py, &record)?, ordinal)).map(|_| ()))
            .map_err(|error| crate::Rejected::new("stream_consumer", error))
    })).map_err(rejected)?;
    Ok((result.records, result.bytes))
}

#[pyfunction]
fn rank_claims(
    py: Python<'_>, sources: Vec<String>, clear_sources: Vec<String>,
    allow_unknown_effective: bool, candidates: Vec<crate::survivorship::Candidate>,
) -> (Vec<usize>, Vec<usize>) {
    py.allow_threads(|| crate::survivorship::rank(&sources, &clear_sources, allow_unknown_effective, &candidates))
}

#[pyfunction]
fn prepare_current_records(py: Python<'_>, readings: &str, as_of: &str, retired: Vec<String>) -> PyResult<String> {
    py.allow_threads(|| crate::readings::prepare_current_records(readings, as_of, &retired))
        .map_err(PyValueError::new_err)
}

#[pyfunction]
fn identify_profile(py: Python<'_>, profile: &str) -> PyResult<String> {
    py.allow_threads(|| crate::readings::identify_profile(profile)).map_err(PyValueError::new_err)
}

#[pyfunction]
fn choose_field_values(py: Python<'_>, command: &str) -> PyResult<String> {
    py.allow_threads(|| crate::field_values::choose_field_values(command)).map_err(PyValueError::new_err)
}

#[pyfunction]
fn describe_field_rules() -> (Vec<String>, Vec<String>) {
    crate::field_values::describe_field_rules()
}

#[pyfunction]
fn prepare_relationship_types(py: Python<'_>, command: &str) -> PyResult<String> {
    py.allow_threads(|| crate::relationship_types::prepare_relationship_types(command)).map_err(PyValueError::new_err)
}

#[pyfunction]
fn prepare_relationships(py: Python<'_>, command: &str) -> PyResult<String> {
    py.allow_threads(|| crate::relationships::prepare_relationships(command)).map_err(PyValueError::new_err)
}

#[pyfunction]
fn prepare_relationship_periods(py: Python<'_>, sightings: &str) -> PyResult<String> {
    py.allow_threads(|| crate::relationships::prepare_relationship_periods(sightings)).map_err(PyValueError::new_err)
}

#[pyfunction]
fn replay_identity(py: Python<'_>, identities: &str, decisions: &str, clock: i64) -> PyResult<String> {
    let identities = serde_json::from_str(identities).map_err(|e| PyValueError::new_err(e.to_string()))?;
    let decisions = serde_json::from_str(decisions).map_err(|e| PyValueError::new_err(e.to_string()))?;
    let state = py.allow_threads(|| crate::identity::replay(identities, decisions, clock))
        .map_err(PyValueError::new_err)?;
    serde_json::to_string(&state).map_err(|e| PyValueError::new_err(e.to_string()))
}

#[pyfunction]
fn replay_record_decisions(py: Python<'_>, command: &str) -> PyResult<String> {
    py.allow_threads(|| crate::decisions::replay_record_decisions(command)).map_err(PyValueError::new_err)
}

#[pyfunction]
fn prepare_master_records(py: Python<'_>, command: &str) -> PyResult<String> {
    py.allow_threads(|| crate::master_records::prepare_master_records(command)).map_err(PyValueError::new_err)
}

#[pyfunction]
fn compare_matching_values(py: Python<'_>, command: &str) -> PyResult<String> {
    py.allow_threads(|| crate::matching_values::compare_matching_values(command)).map_err(PyValueError::new_err)
}

#[pyfunction]
fn apply_record_rules(py: Python<'_>, command: &str) -> PyResult<String> {
    py.allow_threads(|| crate::record_tests::apply_record_rules(command)).map_err(PyValueError::new_err)
}

#[pyfunction]
fn plan_record_matches(py: Python<'_>, command: &str) -> PyResult<String> {
    py.allow_threads(|| crate::record_matches::plan_record_matches(command)).map_err(PyValueError::new_err)
}

#[pyfunction]
fn link_matching_records(py: Python<'_>, command: &str) -> PyResult<String> {
    py.allow_threads(|| crate::record_matches::link_matching_records(command)).map_err(PyValueError::new_err)
}

#[pyfunction]
fn compare_record_pairs(py: Python<'_>, command: &str) -> PyResult<String> {
    py.allow_threads(|| crate::record_pairs::compare_record_pairs(command)).map_err(PyValueError::new_err)
}

#[pyfunction]
fn prepare_record_history(py: Python<'_>, command: &str) -> PyResult<String> {
    py.allow_threads(|| crate::record_history::prepare_record_history(command)).map_err(PyValueError::new_err)
}

#[pyfunction]
fn plan_affected_records(py: Python<'_>, command: &str) -> PyResult<String> {
    py.allow_threads(|| crate::affected_records::plan_affected_records(command)).map_err(PyValueError::new_err)
}

#[pyfunction]
fn prepare_record_lookups(py: Python<'_>, command: &str) -> PyResult<String> {
    py.allow_threads(|| crate::record_lookups::prepare_record_lookups(command)).map_err(PyValueError::new_err)
}

#[pyfunction]
fn prepare_scope_lookups(py: Python<'_>, command: &str) -> PyResult<String> {
    py.allow_threads(|| crate::record_lookups::prepare_scope_lookups(command)).map_err(PyValueError::new_err)
}

#[pyfunction]
fn resolve_record_bindings(py: Python<'_>, command: &str) -> PyResult<String> {
    py.allow_threads(|| crate::decisions::resolve_record_bindings(command)).map_err(PyValueError::new_err)
}
