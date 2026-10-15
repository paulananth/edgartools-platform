//! Configured collections and joins over authenticated, bounded readings.
//! Payloads remain opaque Python objects: their integers, floats and canonical
//! spelling must never round-trip through serde_json. Python supplies its
//! existing canonical equality function and owns receipt encoding/publication.
use std::cmp::Ordering;
use std::collections::{HashMap, HashSet};

use indexmap::IndexMap;
use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use pyo3::types::{PyBool, PyBytes, PyDict, PyFloat, PyInt, PyList, PyString};

fn fail(message: impl Into<String>) -> PyErr {
    PyValueError::new_err(message.into())
}
fn item<'py>(row: &Bound<'py, PyDict>, column: &str) -> PyResult<Bound<'py, PyAny>> {
    row.get_item(column)?
        .ok_or_else(|| fail(format!("Combination row has no column {column}")))
}
fn text(spec: &Bound<'_, PyDict>, name: &str) -> PyResult<String> {
    item(spec, name)?.extract()
}
fn flag(spec: &Bound<'_, PyDict>, name: &str) -> PyResult<bool> {
    item(spec, name)?.extract()
}
fn optional_flag(spec: &Bound<'_, PyDict>, name: &str) -> PyResult<bool> {
    spec.get_item(name)?
        .map_or(Ok(false), |value| value.extract())
}
fn names(spec: &Bound<'_, PyDict>, name: &str) -> PyResult<Vec<String>> {
    item(spec, name)?.extract()
}

#[derive(Clone, PartialEq, Eq, Hash)]
enum Key {
    Text(Vec<u8>),
    Integer(String),
}
fn key(value: &Bound<'_, PyAny>) -> PyResult<Option<Key>> {
    if value.is_none() {
        return Ok(None);
    }
    if value.is_exact_instance_of::<PyString>() {
        return Ok(Some(Key::Text(python_text(value)?)));
    }
    if value.is_exact_instance_of::<PyInt>() {
        return Ok(Some(Key::Integer(value.str()?.to_str()?.into())));
    }
    Err(fail(
        "Combination keys must be text, integer or null; no implicit conversion",
    ))
}

#[derive(Clone)]
enum Scalar {
    Text(Vec<u8>),
    Integer(String),
    Float(f64),
    Bool(bool),
}
impl Scalar {
    fn kind(&self) -> u8 {
        match self {
            Self::Text(_) => 0,
            Self::Integer(_) => 1,
            Self::Float(_) => 2,
            Self::Bool(_) => 3,
        }
    }
    fn compare(&self, other: &Self) -> Ordering {
        match (self, other) {
            (Self::Text(a), Self::Text(b)) => a.cmp(b),
            (Self::Integer(a), Self::Integer(b)) => integer_compare(a, b),
            (Self::Float(a), Self::Float(b)) => a.partial_cmp(b).unwrap_or(Ordering::Equal),
            (Self::Bool(a), Self::Bool(b)) => a.cmp(b),
            _ => self.kind().cmp(&other.kind()), // Homogeneity checked before sorting.
        }
    }
}
fn integer_compare(a: &str, b: &str) -> Ordering {
    let an = a.starts_with('-');
    let bn = b.starts_with('-');
    if an != bn {
        return bn.cmp(&an);
    }
    let aa = a.trim_start_matches('-');
    let bb = b.trim_start_matches('-');
    let order = aa.len().cmp(&bb.len()).then_with(|| aa.cmp(bb));
    if an {
        order.reverse()
    } else {
        order
    }
}
fn scalar(value: &Bound<'_, PyAny>, message: &str) -> PyResult<Scalar> {
    if value.is_exact_instance_of::<PyString>() {
        Ok(Scalar::Text(python_text(value)?))
    } else if value.is_exact_instance_of::<PyInt>() {
        Ok(Scalar::Integer(value.str()?.to_str()?.into()))
    } else if value.is_exact_instance_of::<PyFloat>() {
        Ok(Scalar::Float(value.extract()?))
    } else if value.is_exact_instance_of::<PyBool>() {
        Ok(Scalar::Bool(value.extract()?))
    } else {
        Err(fail(message))
    }
}
// UTF-8 with surrogatepass is injective and orders by Python code points,
// including escaped lone surrogates accepted by the authenticated JSON codec.
// Most strings use the fast valid-UTF-8 path. Payloads are never re-encoded.
fn python_text(value: &Bound<'_, PyAny>) -> PyResult<Vec<u8>> {
    let text = value.downcast::<PyString>()?;
    if let Ok(text) = text.to_str() {
        return Ok(text.as_bytes().to_vec());
    }
    let encoded = value.call_method1("encode", ("utf-8", "surrogatepass"))?;
    Ok(encoded.downcast::<PyBytes>()?.as_bytes().to_vec())
}
fn canonical(value: &Bound<'_, PyAny>, function: &Bound<'_, PyAny>) -> PyResult<Vec<u8>> {
    python_text(&function.call1((value,))?)
}

fn rows<'py>(
    spec: &Bound<'py, PyDict>,
    inputs: &Bound<'py, PyDict>,
    canon: &Bound<'py, PyAny>,
    mut consume: impl FnMut(Bound<'py, PyDict>) -> PyResult<()>,
) -> PyResult<()> {
    let sources = item(spec, "source")?;
    let sources: Vec<String> = if sources.is_instance_of::<PyString>() {
        vec![sources.extract()?]
    } else {
        sources.extract()?
    };
    let table = text(spec, "table")?;
    let checks = item(spec, "checks")?;
    let checks = checks.downcast::<PyDict>()?;
    let filters = item(spec, "where")?;
    let filters = filters.downcast::<PyDict>()?;
    for source in sources {
        let input = item(inputs, &source)?;
        let input = input.downcast::<PyDict>()?;
        let artifacts = item(input, "artifacts")?;
        let artifacts = artifacts.downcast::<PyList>()?;
        for artifact in artifacts.iter() {
            let artifact = artifact.downcast::<PyDict>()?;
            let tables = item(artifact, "tables")?;
            let tables = tables.downcast::<PyDict>()?;
            let records = tables
                .get_item(&table)?
                .ok_or_else(|| fail(format!("Combination reading has no table {table}")))?;
            for row in records.downcast::<PyList>()?.iter() {
                let row = row.downcast::<PyDict>()?;
                for (column, expected) in checks.iter() {
                    let column: String = column.extract()?;
                    if canonical(&item(row, &column)?, canon)? != canonical(&expected, canon)? {
                        return Err(fail(format!("Combination row check failed: {column}")));
                    }
                }
                let mut selected = true;
                for (column, expected) in filters.iter() {
                    let column: String = column.extract()?;
                    // Validate every filter column even after an earlier mismatch.
                    selected &=
                        canonical(&item(row, &column)?, canon)? == canonical(&expected, canon)?;
                }
                if selected {
                    consume(row.clone())?;
                }
            }
        }
    }
    Ok(())
}

struct Pair {
    order: Vec<Scalar>,
    payload: usize,
}
fn group(
    py: Python<'_>,
    spec: &Bound<'_, PyDict>,
    inputs: &Bound<'_, PyDict>,
    canon: &Bound<'_, PyAny>,
    maximum: usize,
) -> PyResult<HashMap<Key, Py<PyAny>>> {
    let key_column = text(spec, "key")?;
    let value_column = text(spec, "value")?;
    let mode = text(spec, "mode")?;
    let collection = mode == "collect" || mode == "collect_flat";
    let order_columns = names(spec, "order_by")?;
    let skip_null = flag(spec, "skip_null_values")?;
    let mut grouped: IndexMap<Key, Vec<Pair>> = IndexMap::new();
    let mut payloads = Vec::new();
    let mut kinds = HashMap::new();
    let mut flattened = 0usize;
    rows(spec, inputs, canon, |row| {
        let Some(key) = key(&item(&row, &key_column)?)? else {
            return Ok(());
        };
        let value = if value_column == "." {
            row.clone().into_any()
        } else {
            item(&row, &value_column)?
        };
        if value.is_none() && skip_null {
            return Ok(());
        }
        if mode == "collect_flat" {
            let values = value.downcast::<PyList>().map_err(|_| {
                fail("collect_flat requires list values; it flattens exactly one level")
            })?;
            flattened = flattened
                .checked_add(values.len())
                .ok_or_else(|| fail("collect_flat exceeds the declared element budget"))?;
            if flattened > maximum {
                return Err(fail("collect_flat exceeds the declared element budget"));
            }
        }
        let mut order = Vec::new();
        for column in &order_columns {
            let value = scalar(
                &item(&row, column)?,
                "Ordering columns must have one exact scalar type and no nulls",
            )?;
            if *kinds.entry(column.clone()).or_insert(value.kind()) != value.kind() {
                return Err(fail(
                    "Ordering columns must have one exact scalar type and no nulls",
                ));
            }
            order.push(value);
        }
        grouped.entry(key).or_default().push(Pair {
            order,
            payload: payloads.len(),
        });
        payloads.push(value.unbind());
        Ok(())
    })?;
    // Stable sorting is independent of Python objects and releases the GIL.
    if !order_columns.is_empty() {
        py.allow_threads(|| {
            for pairs in grouped.values_mut() {
                pairs.sort_by(|a, b| {
                    a.order
                        .iter()
                        .zip(&b.order)
                        .map(|(a, b)| a.compare(b))
                        .find(|o| !o.is_eq())
                        .unwrap_or(Ordering::Equal)
                });
            }
        });
    }
    let distinct = flag(spec, "distinct")?;
    let skip_empty = optional_flag(spec, "skip_empty_text")?;
    let sort_values = optional_flag(spec, "sort_values")?;
    let mut result = HashMap::new();
    for (key, pairs) in grouped {
        let mut values = Vec::new();
        let mut seen = HashSet::new();
        for pair in pairs {
            let value = payloads[pair.payload].bind(py);
            let items: Vec<Bound<'_, PyAny>> = if mode == "collect_flat" {
                value.downcast::<PyList>()?.iter().collect()
            } else {
                vec![value.clone()]
            };
            for item in items {
                if skip_empty && item.is_exact_instance_of::<PyString>() && item.len()? == 0 {
                    continue;
                }
                if distinct && !seen.insert(canonical(&item, canon)?) {
                    continue;
                }
                values.push(item.unbind());
            }
        }
        if sort_values {
            let mut ordered = Vec::new();
            let mut kind = None;
            for (index, value) in values.iter().enumerate() {
                let value = scalar(
                    value.bind(py),
                    "sort_values requires one exact scalar type and no nulls",
                )?;
                if *kind.get_or_insert(value.kind()) != value.kind() {
                    return Err(fail(
                        "sort_values requires one exact scalar type and no nulls",
                    ));
                }
                ordered.push((value, index));
            }
            py.allow_threads(|| ordered.sort_by(|a, b| a.0.compare(&b.0)));
            values = ordered
                .into_iter()
                .map(|(_, i)| values[i].clone_ref(py))
                .collect();
        }
        if mode == "one" && values.len() != 1 {
            return Err(fail("Group one requires exactly one value per key"));
        }
        let value = if collection {
            PyList::new(py, values)?.into_any().unbind()
        } else {
            values
                .get(if mode == "first" {
                    0
                } else {
                    values.len().saturating_sub(1)
                })
                .ok_or_else(|| fail("Group requires a value"))?
                .clone_ref(py)
        };
        result.insert(key, value);
    }
    Ok(result)
}

fn join_field(
    output: &Bound<'_, PyDict>,
    path: &[String],
    replace: bool,
    value: &Bound<'_, PyAny>,
) -> PyResult<()> {
    let mut parent = output.clone();
    for part in &path[..path.len() - 1] {
        let child = parent.get_item(part)?;
        let next = match child {
            None => PyDict::new(output.py()),
            Some(value) if value.is_none() => PyDict::new(output.py()),
            Some(value) => value
                .downcast::<PyDict>()
                .map_err(|_| fail("Nested join parent must be an object or null"))?
                .copy()?,
        };
        parent.set_item(part, &next)?;
        parent = next;
    }
    let leaf = &path[path.len() - 1];
    if parent.contains(leaf)? && !replace {
        return Err(fail(format!(
            "Join would overwrite column {leaf}; declare replace explicitly"
        )));
    }
    parent.set_item(leaf, value)
}

#[pyfunction]
pub fn combine_tables(
    py: Python<'_>,
    plan: &Bound<'_, PyDict>,
    inputs: &Bound<'_, PyDict>,
    canon: &Bound<'_, PyAny>,
) -> PyResult<Py<PyDict>> {
    let maximum: usize = item(plan, "max_rows")?.extract()?;
    if maximum == 0 || maximum > 40_000_000 {
        return Err(fail("Combination max_rows must be 1..40000000"));
    }
    let specs = item(plan, "groups")?;
    let specs = specs.downcast::<PyDict>()?;
    let mut groups = HashMap::new();
    let mut collection = HashSet::new();
    for (name, spec) in specs.iter() {
        let name: String = name.extract()?;
        let spec = spec.downcast::<PyDict>()?;
        if ["collect", "collect_flat"].contains(&text(spec, "mode")?.as_str()) {
            collection.insert(name.clone());
        }
        groups.insert(name, group(py, spec, inputs, canon, maximum)?);
    }
    let tables = item(plan, "tables")?;
    let tables = tables.downcast::<PyDict>()?;
    let result = PyDict::new(py);
    let mut count = 0usize;
    for (name, spec) in tables.iter() {
        let spec = spec.downcast::<PyDict>()?;
        let joins = item(spec, "joins")?;
        let joins = joins.downcast::<PyDict>()?;
        let mut joins_ordered = Vec::new();
        for (field, join) in joins.iter() {
            let field: String = field.extract()?;
            let join = join.downcast::<PyDict>()?.clone();
            let explicit = join.contains("path")?;
            let path: Vec<String> = if explicit {
                names(&join, "path")?
            } else {
                vec![field.clone()]
            };
            if path.is_empty() || path.len() > 8 {
                return Err(fail("Join path names 1..8 columns"));
            }
            joins_ordered.push((field, join, path, explicit));
        }
        joins_ordered.sort_by_key(|(_, _, path, _)| path.len());
        let output_rows = PyList::empty(py);
        rows(spec, inputs, canon, |row| {
            let output = row.copy()?;
            for (field, join, path, explicit) in &joins_ordered {
                let missing = text(join, "on_missing")?;
                let replace = flag(join, "replace")?;
                if !explicit && missing != "skip" && output.contains(field)? && !replace {
                    return Err(fail(format!(
                        "Join would overwrite column {field}; declare replace explicitly"
                    )));
                }
                let key = key(&item(&row, &text(join, "key")?)?)?;
                let group_name = text(join, "group")?;
                let group = groups
                    .get(&group_name)
                    .ok_or_else(|| fail("Unknown combination group"))?;
                let default;
                let value = match key.as_ref().and_then(|key| group.get(key)) {
                    Some(value) => value.bind(py),
                    None => {
                        if missing == "error" {
                            return Err(fail(format!("No combination group match for {field}")));
                        }
                        if missing == "skip" {
                            continue;
                        }
                        default = if collection.contains(&group_name) {
                            PyList::empty(py).into_any().unbind()
                        } else {
                            py.None()
                        };
                        default.bind(py)
                    }
                };
                join_field(&output, path, replace, value)?;
            }
            if let Some(drop) = spec.get_item("drop")? {
                for column in drop.extract::<Vec<String>>()? {
                    if !output.contains(&column)? {
                        return Err(fail(format!("Drop names missing output column {column}")));
                    }
                    output.del_item(column)?;
                }
            }
            output_rows.append(output)?;
            count += 1;
            if count > maximum {
                return Err(fail("Combination exceeds output row budget"));
            }
            Ok(())
        })?;
        result.set_item(name, output_rows)?;
    }
    Ok(result.unbind())
}
