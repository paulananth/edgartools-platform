//! The Python binding (`--features python`, built by maturin). Python reaches
//! the engine only through `edgar_warehouse/rules/source_engine.py`.

use pyo3::create_exception;
use pyo3::exceptions::PyException;
use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList};
use pyo3::IntoPyObjectExt;

use crate::{Engine, Lookups, Raw, Rejected, Step, Steps, Val};

create_exception!(source_contract, SourceRejected, PyException);

fn rejected(error: Rejected) -> PyErr {
    SourceRejected::new_err((error.code, error.detail))
}

fn to_py(py: Python<'_>, value: &Val) -> PyResult<PyObject> {
    match value {
        Val::Null => Ok(py.None()),
        Val::Int(i) => i.into_py_any(py),
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

    #[pyo3(signature = (data, lookups, context="{}"))]
    fn read(&self, py: Python<'_>, data: &[u8], lookups: &Bound<'_, PyDict>, context: &str) -> PyResult<PyObject> {
        let mut sets = Lookups::new();
        for (name, values) in lookups.iter() {
            let values: Vec<String> = values.try_iter()?.map(|v| v?.extract()).collect::<PyResult<_>>()?;
            sets.insert(name.extract()?, values.into_iter().collect());
        }
        let context = crate::context::from_json(context).map_err(rejected)?;
        // Other Python threads run while the engine reads; a step takes the
        // interpreter back for its own call.
        let reading = py.allow_threads(|| self.inner.read_with_context(data, &sets, &context)).map_err(rejected)?;
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
}

#[pymodule]
fn source_contract(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<PyEngine>()?;
    m.add("SourceRejected", m.py().get_type::<SourceRejected>())?;
    Ok(())
}
