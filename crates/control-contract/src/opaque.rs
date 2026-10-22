//! Canonical equality for opaque Python values that contain lone surrogates.
//! Rust sorts and assembles containers; Python's JSON codec transports scalars.
use pyo3::basic::CompareOp;
use pyo3::exceptions::{PyTypeError, PyValueError};
use pyo3::prelude::*;
use pyo3::types::{PyBool, PyBytes, PyDict, PyFloat, PyInt, PyList, PyString, PyTuple};
use std::cmp::Ordering;
use std::collections::HashSet;

struct Encoder<'py> {
    dumps: Bound<'py, PyAny>,
    options: Bound<'py, PyDict>,
    active: HashSet<usize>,
}

impl Encoder<'_> {
    fn scalar(&self, value: &Bound<'_, PyAny>) -> PyResult<Vec<u8>> {
        let encoded = self
            .dumps
            .call((value,), Some(&self.options))?
            .call_method1("encode", ("utf-8", "surrogatepass"))?;
        Ok(encoded.downcast::<PyBytes>()?.as_bytes().to_vec())
    }

    fn value(&mut self, value: &Bound<'_, PyAny>) -> PyResult<Vec<u8>> {
        let container = value.is_instance_of::<PyDict>()
            || value.is_instance_of::<PyList>()
            || value.is_instance_of::<PyTuple>();
        if !container {
            return self.scalar(value);
        }
        let identity = value.as_ptr() as usize;
        if !self.active.insert(identity) {
            return Err(PyValueError::new_err("Circular reference detected"));
        }
        let result = self.container(value);
        self.active.remove(&identity);
        result
    }

    fn container(&mut self, value: &Bound<'_, PyAny>) -> PyResult<Vec<u8>> {
        let mut output = Vec::new();
        if let Ok(object) = value.downcast::<PyDict>() {
            let mut entries: Vec<_> = object.iter().collect();
            let mut failure = None;
            entries.sort_by(|(left, _), (right, _)| {
                if failure.is_some() {
                    return Ordering::Equal;
                }
                let compare = || -> PyResult<Ordering> {
                    if left.rich_compare(right, CompareOp::Lt)?.is_truthy()? {
                        return Ok(Ordering::Less);
                    }
                    if right.rich_compare(left, CompareOp::Lt)?.is_truthy()? {
                        return Ok(Ordering::Greater);
                    }
                    Ok(Ordering::Equal)
                };
                match compare() {
                    Ok(order) => order,
                    Err(error) => {
                        failure = Some(error);
                        Ordering::Equal
                    }
                }
            });
            if let Some(error) = failure {
                return Err(error);
            }
            output.push(b'{');
            for (index, (key, item)) in entries.iter().enumerate() {
                if index != 0 {
                    output.push(b',');
                }
                if key.is_instance_of::<PyString>() {
                    output.extend(self.scalar(key)?);
                } else if key.is_none()
                    || key.is_instance_of::<PyBool>()
                    || key.is_instance_of::<PyInt>()
                    || key.is_instance_of::<PyFloat>()
                {
                    output.push(b'"');
                    output.extend(self.scalar(key)?);
                    output.push(b'"');
                } else {
                    return Err(PyTypeError::new_err(
                        "JSON object keys must be strings, numbers, booleans or null",
                    ));
                }
                output.push(b':');
                output.extend(self.value(item)?);
            }
            output.push(b'}');
        } else {
            output.push(b'[');
            for (index, item) in value.try_iter()?.enumerate() {
                if index != 0 {
                    output.push(b',');
                }
                output.extend(self.value(&item?)?);
            }
            output.push(b']');
        }
        Ok(output)
    }
}

pub fn canonicalize(py: Python<'_>, value: &Bound<'_, PyAny>) -> PyResult<Py<PyAny>> {
    let options = PyDict::new(py);
    options.set_item("ensure_ascii", false)?;
    options.set_item("allow_nan", false)?;
    let mut encoder = Encoder {
        dumps: py.import("json")?.getattr("dumps")?,
        options,
        active: HashSet::new(),
    };
    let encoded = encoder.value(value)?;
    Ok(PyBytes::new(py, &encoded)
        .call_method1("decode", ("utf-8", "surrogatepass"))?
        .unbind())
}
