#include <Python.h>
#include <string>
#include <vector>
#include <map>
#include <stdexcept>

struct ThValue {
    enum Kind {
        K_Float64,
        K_Int64,
        K_Bool,
        K_String,
        K_List,
        K_Dict,
        K_Struct,
        K_Class,
        K_None
    } kind;

    double f64;
    long long i64;
    bool b;
    std::string s;
    std::vector<ThValue> list;
    std::map<std::string, ThValue> dict;

    PyObject* pyobj = nullptr;

    ThValue() : kind(K_None), f64(0.0), i64(0), b(false), pyobj(nullptr) {}
};

struct ThStructView {
    PyObject* pyobj;

    ThStructView(PyObject* obj) : pyobj(obj) {
        if (!PyDict_Check(obj))
            throw std::runtime_error("Expected Python dict for struct view");
    }

    bool has_field(const std::string& name) const {
        return PyDict_GetItemString(pyobj, name.c_str()) != nullptr;
    }

    ThValue get_field(const std::string& name) const;
};

struct ThClassInstance {
    PyObject* pyobj;

    ThClassInstance(PyObject* obj) : pyobj(obj) {
    }

    bool has_attr(const std::string& name) const {
        return PyObject_HasAttrString(pyobj, name.c_str());
    }

    ThValue get_attr(const std::string& name) const;
    ThValue call_method(const std::string& name,
                        const std::vector<ThValue>& args) const;
};

static ThValue py_to_th(PyObject* obj);

static ThValue py_to_float64(PyObject* obj) {
    ThValue v;
    v.kind = ThValue::K_Float64;
    v.f64 = PyFloat_AsDouble(obj);
    return v;
}

static ThValue py_to_int64(PyObject* obj) {
    ThValue v;
    v.kind = ThValue::K_Int64;
    v.i64 = PyLong_AsLongLong(obj);
    return v;
}

static ThValue py_to_bool(PyObject* obj) {
    ThValue v;
    v.kind = ThValue::K_Bool;
    v.b = PyObject_IsTrue(obj);
    return v;
}

static ThValue py_to_string(PyObject* obj) {
    ThValue v;
    v.kind = ThValue::K_String;
    v.s = PyUnicode_AsUTF8(obj);
    return v;
}

static ThValue py_to_list(PyObject* obj) {
    ThValue v;
    v.kind = ThValue::K_List;

    Py_ssize_t n = PySequence_Size(obj);
    v.list.reserve(n);

    for (Py_ssize_t i = 0; i < n; i++) {
        PyObject* item = PySequence_GetItem(obj, i);
        v.list.push_back(py_to_th(item));
        Py_DECREF(item);
    }

    return v;
}

static ThValue py_to_dict(PyObject* obj) {
    ThValue v;
    v.kind = ThValue::K_Dict;

    PyObject *key, *value;
    Py_ssize_t pos = 0;

    while (PyDict_Next(obj, &pos, &key, &value)) {
        std::string k = PyUnicode_AsUTF8(key);
        v.dict[k] = py_to_th(value);
    }

    return v;
}

static ThValue py_to_struct(PyObject* obj) {
    if (!PyDict_Check(obj))
        throw std::runtime_error("Expected dict for struct");

    ThValue v;
    v.kind = ThValue::K_Struct;
    v.pyobj = obj; 
    Py_INCREF(obj);
    return v;
}

static ThValue py_to_class(PyObject* obj) {
    ThValue v;
    v.kind = ThValue::K_Class;
    v.pyobj = obj;
    Py_INCREF(obj);
    return v;
}

static ThValue py_to_th(PyObject* obj) {
    if (obj == Py_None) {
        ThValue v;
        v.kind = ThValue::K_None;
        return v;
    }

    if (PyFloat_Check(obj)) return py_to_float64(obj);
    if (PyLong_Check(obj))  return py_to_int64(obj);
    if (PyBool_Check(obj))  return py_to_bool(obj);
    if (PyUnicode_Check(obj)) return py_to_string(obj);
    if (PyList_Check(obj) || PyTuple_Check(obj)) return py_to_list(obj);
    if (PyDict_Check(obj)) return py_to_dict(obj);

    return py_to_class(obj);
}

static PyObject* th_to_py(const ThValue& v);

static PyObject* th_to_py_float64(const ThValue& v) {
    return PyFloat_FromDouble(v.f64);
}

static PyObject* th_to_py_int64(const ThValue& v) {
    return PyLong_FromLongLong(v.i64);
}

static PyObject* th_to_py_bool(const ThValue& v) {
    return PyBool_FromLong(v.b ? 1 : 0);
}

static PyObject* th_to_py_string(const ThValue& v) {
    return PyUnicode_FromString(v.s.c_str());
}

static PyObject* th_to_py_list(const ThValue& v) {
    PyObject* list = PyList_New(v.list.size());
    for (size_t i = 0; i < v.list.size(); i++) {
        PyList_SetItem(list, i, th_to_py(v.list[i]));
    }
    return list;
}

static PyObject* th_to_py_dict(const ThValue& v) {
    PyObject* dict = PyDict_New();
    for (auto& [k, val] : v.dict) {
        PyDict_SetItemString(dict, k.c_str(), th_to_py(val));
    }
    return dict;
}

static PyObject* th_to_py_struct(const ThValue& v) {
    Py_INCREF(v.pyobj);
    return v.pyobj;
}

static PyObject* th_to_py_class(const ThValue& v) {
    Py_INCREF(v.pyobj);
    return v.pyobj;
}

static PyObject* th_to_py(const ThValue& v) {
    switch (v.kind) {
        case ThValue::K_Float64: return th_to_py_float64(v);
        case ThValue::K_Int64:   return th_to_py_int64(v);
        case ThValue::K_Bool:    return th_to_py_bool(v);
        case ThValue::K_String:  return th_to_py_string(v);
        case ThValue::K_List:    return th_to_py_list(v);
        case ThValue::K_Dict:    return th_to_py_dict(v);
        case ThValue::K_Struct:  return th_to_py_struct(v);
        case ThValue::K_Class:   return th_to_py_class(v);
        case ThValue::K_None:    Py_RETURN_NONE;
    }
    Py_RETURN_NONE;
}

ThValue ThStructView::get_field(const std::string& name) const {
    PyObject* val = PyDict_GetItemString(pyobj, name.c_str()); // borrowed
    if (!val)
        throw std::runtime_error("Struct field not found: " + name);
    return py_to_th(val);
}

ThValue ThClassInstance::get_attr(const std::string& name) const {
    PyObject* val = PyObject_GetAttrString(pyobj, name.c_str()); // new ref
    if (!val)
        throw std::runtime_error("Class attribute not found: " + name);
    ThValue out = py_to_th(val);
    Py_DECREF(val);
    return out;
}

ThValue ThClassInstance::call_method(const std::string& name,
                                     const std::vector<ThValue>& args) const {
    PyObject* f = PyObject_GetAttrString(pyobj, name.c_str()); // new ref
    if (!f || !PyCallable_Check(f)) {
        Py_XDECREF(f);
        throw std::runtime_error("Method not callable: " + name);
    }

    PyObject* tuple = PyTuple_New(args.size());
    for (size_t i = 0; i < args.size(); i++) {
        PyTuple_SetItem(tuple, i, th_to_py(args[i]));
    }

    PyObject* r = PyObject_CallObject(f, tuple);
    Py_DECREF(f);
    Py_DECREF(tuple);

    if (!r)
        throw std::runtime_error("Python method call failed");

    ThValue out = py_to_th(r);
    Py_DECREF(r);
    return out;
}

struct ThMethodDesc {
    std::string name;
    ThValue (*impl)(const std::vector<ThValue>& args);
};

struct ThClassDesc {
    std::string name;
    std::vector<std::string> field_names;
    std::vector<ThMethodDesc> methods;
};

static PyTypeObject* create_python_class(const ThClassDesc& desc) {
    PyTypeObject* type = (PyTypeObject*)PyType_Type.tp_alloc(&PyType_Type, 0);
    if (!type)
        throw std::runtime_error("Failed to allocate PyTypeObject");

    type->tp_name = desc.name.c_str();
    type->tp_basicsize = sizeof(PyObject);
    type->tp_flags = Py_TPFLAGS_DEFAULT | Py_TPFLAGS_BASETYPE;
    type->tp_new = PyType_GenericNew;

    if (PyType_Ready(type) < 0)
        throw std::runtime_error("PyType_Ready failed");

    return type;
}

static ThClassInstance make_python_class_instance(const ThClassDesc& desc,
                                                  const std::map<std::string, ThValue>& field_values) {
    PyTypeObject* type = create_python_class(desc);
    PyObject* obj = type->tp_new(type, nullptr, nullptr);
    if (!obj)
        throw std::runtime_error("Failed to create Python class instance");

    for (auto& [name, val] : field_values) {
        PyObject* pyv = th_to_py(val);
        if (PyObject_SetAttrString(obj, name.c_str(), pyv) < 0) {
            Py_DECREF(pyv);
            Py_DECREF(obj);
            throw std::runtime_error("Failed to set attribute: " + name);
        }
        Py_DECREF(pyv);
    }

    return ThClassInstance(obj);
}

extern "C" ThStructView threadon_make_struct_from_py(PyObject* dict) {
    if (!PyDict_Check(dict))
        throw std::runtime_error("threadon_make_struct_from_py: expected dict");
    return ThStructView(dict);
}

extern "C" ThClassInstance threadon_make_class_from_py(PyObject* obj) {
    return ThClassInstance(obj);
}

extern "C" PyObject* threadon_make_pyclass_from_desc(const char* name,
                                                     ThValue* fields,
                                                     const char** field_names,
                                                     int field_count) {
    ThClassDesc desc;
    desc.name = name;
    for (int i = 0; i < field_count; i++) {
        desc.field_names.push_back(field_names[i]);
    }

    std::map<std::string, ThValue> fv;
    for (int i = 0; i < field_count; i++) {
        fv[field_names[i]] = fields[i];
    }

    ThClassInstance inst = make_python_class_instance(desc, fv);
    Py_INCREF(inst.pyobj);
    return inst.pyobj;
}

extern "C" void threadon_python_bridge_init() {
    if (!Py_IsInitialized())
        Py_Initialize();
}
