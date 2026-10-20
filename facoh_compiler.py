import ast
import hashlib
import os
import platform
import subprocess
import sys
import sysconfig
import tempfile
from pathlib import Path

import llvmlite.binding as llvm
from lexer import Lexer
from llvmlite import ir
from parser import Parser

# Initialize LLVM binding infrastructure for in-memory optimization passes
# llvm.initialize()
llvm.initialize_native_target()
llvm.initialize_native_asmprinter()

RUNTIME_C = r'''#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <ctype.h>
#include <setjmp.h>
#include <Python.h>
#ifndef _WIN32
#include <sched.h>
#else
#include <windows.h>
#endif

enum { V_INT=1, V_FLOAT=2, V_BOOL=3, V_STRING=4, V_LIST=5, V_NONE=6, V_TUPLE=7, V_SET=8, V_DICT=9, V_OBJECT=10, V_PYOBJECT=11, V_UNBOUND=12, V_ITERATOR=13, V_RANGE=14 };
typedef struct Value Value;
struct Value {
    int32_t tag;
    int32_t reserved;
    union { int64_t i; double f; int b; char *s; void *py; struct { Value **items; int64_t len, cap; } list; struct { char *name; Value **items; int64_t len, cap; } object; struct { Value *source; int64_t index; PyObject *iterator; Value *pending; int done; } iter; struct { int64_t start, stop, step, count; } range; } as;
};
static void facoh_py_init(void);
static void facoh_py_error(const char *fallback);
static PyObject *facoh_to_py(Value *v);
int64_t facoh_to_i64(Value *v);
static double number(Value *v);
static Value *facoh_from_py(PyObject *o);
Value *facoh_py_method_call(Value *obj, const char *method, Value **args, int64_t count, const char **kw_names, Value **kw_values, int64_t kw_count);
Value *facoh_native_function(const char *name, void *function, const char **parameter_names, int64_t arity);
Value *facoh_py_call_value(Value *callable, Value **args, int64_t count, const char **kw_names, Value **kw_values, int64_t kw_count);
Value *facoh_method_call_kw(Value *obj, const char *method, Value **args, int64_t count, const char **kw_names, Value **kw_values, int64_t kw_count);
static Value *facoh_builtin_method_call(Value *obj, const char *method, Value **args, int64_t count, const char **kw_names, Value **kw_values, int64_t kw_count);
Value *facoh_dict_new(void);
void facoh_dict_set(Value *v, Value *key, Value *item);
static jmp_buf *facoh_active_handler = NULL;
static char facoh_current_error_type[128] = "Error";
static char facoh_current_error_message[1024] = "";
static Value *facoh_current_error_object = NULL;
typedef struct { char name[128]; char parent[128]; } FacohClassEntry;
typedef struct { char class_name[128]; char method_name[128]; void *function; int64_t arity; char parameter_names[32][64]; } FacohMethodEntry;
static FacohClassEntry facoh_classes[256]; static int facoh_class_count=0;
static FacohMethodEntry facoh_methods[1024]; static int facoh_method_count=0;
void facoh_register_object(const char *name, const char *parent) {
    for(int i=0;i<facoh_class_count;i++) if(strcmp(facoh_classes[i].name,name)==0) { snprintf(facoh_classes[i].parent,sizeof(facoh_classes[i].parent),"%s",parent?parent:""); return; }
    if(facoh_class_count>=256) return;
    snprintf(facoh_classes[facoh_class_count].name,sizeof(facoh_classes[facoh_class_count].name),"%s",name);
    snprintf(facoh_classes[facoh_class_count].parent,sizeof(facoh_classes[facoh_class_count].parent),"%s",parent?parent:""); facoh_class_count++;
}
void facoh_register_method(const char *class_name, const char *method_name, void *function, int64_t arity, const char **parameter_names, int64_t parameter_count) {
    if(facoh_method_count>=1024) return;
    FacohMethodEntry *entry=&facoh_methods[facoh_method_count++];
    snprintf(entry->class_name,sizeof(entry->class_name),"%s",class_name);
    snprintf(entry->method_name,sizeof(entry->method_name),"%s",method_name);
    entry->function=function; entry->arity=arity;
    for(int64_t i=0;i<parameter_count && i<32;i++) snprintf(entry->parameter_names[i],sizeof(entry->parameter_names[i]),"%s",parameter_names[i]);
}
static const char *facoh_parent_of(const char *name) {
    for(int i=0;i<facoh_class_count;i++) if(strcmp(facoh_classes[i].name,name)==0) return facoh_classes[i].parent;
    return "";
}

void *facoh_handler_get(void) { return (void *)facoh_active_handler; }
void facoh_handler_set(void *p) { facoh_active_handler = (jmp_buf *)p; }
static const char *facoh_error_display_name(const char *type) {
    static const char *names[][2]={{"Error","FACOHError"},{"SyntaxError","FACOHSyntaxError"},{"IndexError","FACOHIndexError"},{"ValueError","FACOHValueError"},{"NonExistantError","FACOHNonExistantError"},{"ZeroDivisionError","FACOHZeroDivisionError"},{"FileNotFoundError","FACOHFileNotFoundError"},{"IndentationError","FACOHIndentationError"},{"TypeError","FACOHTypeError"},{"KeyError","FACOHKeyError"},{"TimeoutError","FACOHTimeoutError"},{"ConnectionError","FACOHConnectionError"},{"OSError","FACOHOSError"}};
    for(size_t i=0;i<sizeof(names)/sizeof(names[0]);i++) if(strcmp(type,names[i][0])==0) return names[i][1];
    return type;
}
_Noreturn static void facoh_raise(const char *type, const char *message) {
    char type_copy[128];
    char message_copy[1024];
    snprintf(type_copy, sizeof(type_copy), "%s", type ? type : "Error");
    snprintf(message_copy, sizeof(message_copy), "%s", message ? message : "");
    snprintf(facoh_current_error_type, sizeof(facoh_current_error_type), "%s", type_copy);
    snprintf(facoh_current_error_message, sizeof(facoh_current_error_message), "%s", message_copy);
    if (facoh_active_handler) longjmp(*facoh_active_handler, 1);
    fprintf(stderr, "%s: %s\n", facoh_error_display_name(facoh_current_error_type), facoh_current_error_message);
    exit(1);
}
int32_t facoh_error_matches(const char *type) {
    if (!type) return 0;
    const char *current=facoh_current_error_type;
    for(int depth=0; current && current[0] && depth<256; depth++) {
        if(strcmp(type,current)==0 || strcmp(type,"Error")==0) return 1;
        current=facoh_parent_of(current);
    }
    return strcmp(type,"Error")==0;
}
void facoh_rethrow(void) { facoh_raise(facoh_current_error_type, facoh_current_error_message); }
#if defined(_MSC_VER)
#define FACOH_TLS __declspec(thread)
#else
#define FACOH_TLS __thread
#endif
/* Values are never individually freed, so hand them out of zeroed per-thread
   chunks instead of paying one calloc() per Value. */
static FACOH_TLS Value *facoh_value_pool = NULL;
static FACOH_TLS size_t facoh_value_pool_left = 0;
static Value *make_value(int tag) {
    if (!facoh_value_pool_left) {
        const size_t chunk = 4096;
        facoh_value_pool = (Value *)calloc(chunk, sizeof(Value));
        if (!facoh_value_pool) { fputs("FACOH runtime: out of memory\n", stderr); exit(1); }
        facoh_value_pool_left = chunk;
    }
    Value *v = facoh_value_pool++; facoh_value_pool_left--;
    v->tag = tag; return v;
}
Value *facoh_int(int64_t x) { Value *v=make_value(V_INT); v->as.i=x; return v; }
Value *facoh_float(double x) { Value *v=make_value(V_FLOAT); v->as.f=x; return v; }
Value *facoh_bool(int x) { Value *v=make_value(V_BOOL); v->as.b=!!x; return v; }
Value *facoh_string(const char *x) { const char *src=x ? x : ""; Value *v=make_value(V_STRING); size_t n=strlen(src)+1; v->as.s=(char*)malloc(n); if(!v->as.s) exit(1); memcpy(v->as.s,src,n); return v; }
Value *facoh_none(void) { return make_value(V_NONE); }
Value *facoh_unbound(void) { return make_value(V_UNBOUND); }
Value *facoh_check_defined(Value *v, const char *name) { if(v && v->tag==V_UNBOUND) { char message[256]; snprintf(message,sizeof(message),"Variable '%s' does not exist",name); facoh_raise("NonExistantError",message); } return v?v:facoh_none(); }
Value *facoh_list_new(void) { return make_value(V_LIST); }
Value *facoh_tuple_new(void) { return make_value(V_TUPLE); }
Value *facoh_collection_new(int tag) { return make_value(tag); }
static int equal_value(Value *a, Value *b);
void facoh_list_push(Value *v, Value *item) {
    if (!v || (v->tag != V_LIST && v->tag != V_TUPLE && v->tag != V_SET)) { facoh_raise("TypeError", "expected collection"); }
    if (v->tag == V_SET) { for (int64_t j=0;j<v->as.list.len;j++) if (equal_value(v->as.list.items[j], item)) return; }
    if (v->as.list.len == v->as.list.cap) {
        int64_t cap = v->as.list.cap ? v->as.list.cap * 2 : 8;
        Value **p=(Value **)realloc(v->as.list.items, (size_t)cap*sizeof(Value*));
        if(!p) exit(1); v->as.list.items=p; v->as.list.cap=cap;
    }
    v->as.list.items[v->as.list.len++]=item;
}
Value *facoh_object_new(const char *name) {
    Value *v = make_value(V_OBJECT);
    v->as.object.name = (char *)malloc(strlen(name ? name : "Object") + 1);
    if (!v->as.object.name) exit(1);
    strcpy(v->as.object.name, name ? name : "Object");
    return v;
}
void facoh_attr_set(Value *obj, const char *name, Value *item) {
    if (obj && obj->tag==V_PYOBJECT) { facoh_py_init(); PyObject *value=facoh_to_py(item); if(!value || PyObject_SetAttrString((PyObject*)obj->as.py,name,value)<0) { Py_XDECREF(value); facoh_py_error("could not assign Python attribute"); } Py_DECREF(value); return; }
    if (!obj || obj->tag != V_OBJECT) { facoh_raise("TypeError", "attribute assignment requires an object"); return; }
    for (int64_t i=0;i<obj->as.object.len;i+=2) {
        Value *key=obj->as.object.items[i];
        if (key && key->tag==V_STRING && strcmp(key->as.s,name)==0) { obj->as.object.items[i+1]=item; return; }
    }
    if (obj->as.object.len + 2 > obj->as.object.cap) {
        int64_t cap=obj->as.object.cap?obj->as.object.cap*2:8;
        while(cap<obj->as.object.len+2) cap*=2;
        Value **items=(Value**)realloc(obj->as.object.items,(size_t)cap*sizeof(Value*));
        if(!items) exit(1); obj->as.object.items=items; obj->as.object.cap=cap;
    }
    obj->as.object.items[obj->as.object.len++]=facoh_string(name);
    obj->as.object.items[obj->as.object.len++]=item;
}
/* Attribute names arrive as constant C strings. Cache an interned str per
   name so each lookup skips PyUnicode_FromString and reuses the cached hash.
   Callers hold the GIL, which serialises access to the cache. */
typedef struct { const char *key; char *copy; PyObject *name; } FacohNameCache;
static FacohNameCache facoh_name_cache[256];
static PyObject *facoh_interned_name(const char *name) {
    size_t slot = (size_t)(((uintptr_t)name >> 3) & 255);
    FacohNameCache *e = &facoh_name_cache[slot];
    if (e->name && e->key == name && strcmp(e->copy, name) == 0) { Py_INCREF(e->name); return e->name; }
    PyObject *fresh = PyUnicode_InternFromString(name);
    if (!fresh) return NULL;
    char *copy = strdup(name);
    if (!copy) { Py_DECREF(fresh); PyErr_NoMemory(); return NULL; }
    if (e->name) { Py_DECREF(e->name); free(e->copy); }
    e->key = name; e->copy = copy; e->name = fresh;
    Py_INCREF(fresh); return fresh;
}
/* Returns a new reference or NULL. Any failure is cleared, matching the old
   GetAttrString + PyErr_Clear behaviour, but a plain missing attribute no
   longer builds and discards an AttributeError. */
static PyObject *facoh_lookup_attr(PyObject *obj, const char *name) {
    PyObject *key = facoh_interned_name(name), *out = NULL;
    if (!key) { PyErr_Clear(); return NULL; }
#if PY_VERSION_HEX >= 0x030D0000
    int rc = PyObject_GetOptionalAttr(obj, key, &out);
#else
    int rc = _PyObject_LookupAttr(obj, key, &out);
#endif
    Py_DECREF(key);
    if (rc < 0) { PyErr_Clear(); return NULL; }
    return out;
}
/* Mapping lookup by cached interned name; returns a new reference or NULL
   with the error left set (same contract as PyMapping_GetItemString). */
static PyObject *facoh_mapping_get(PyObject *map, const char *name) {
    PyObject *key = facoh_interned_name(name);
    if (!key) return NULL;
    PyObject *out = PyObject_GetItem(map, key);
    Py_DECREF(key);
    return out;
}
Value *facoh_attr_get(Value *obj, const char *name) {
    if (obj && obj->tag==V_PYOBJECT) { 
        facoh_py_init(); 
        PyObject *py_obj = (PyObject*)obj->as.py;
        PyObject *value = facoh_lookup_attr(py_obj, name); 
        if (!value) { 
            const char *maps[] = {"FUNCTIONS", "OBJECTS"};
            for(int m=0; m<2; m++) {
                PyObject *exports = facoh_lookup_attr(py_obj, maps[m]);
                if(exports) {
                    value = facoh_mapping_get(exports, name);
                    Py_DECREF(exports);
                    if(value) break;
                    PyErr_Clear();
                } else {
                    PyErr_Clear();
                }
            }
        }
        if(!value) { facoh_py_error("Python attribute does not exist"); return facoh_none(); } 
        Value *out=facoh_from_py(value); Py_DECREF(value); return out; 
    }
    if (!obj || obj->tag != V_OBJECT) { facoh_raise("TypeError", "attribute access requires an object"); return facoh_none(); }
    for (int64_t i=0;i<obj->as.object.len;i+=2) {
        Value *key=obj->as.object.items[i];
        if (key && key->tag==V_STRING && strcmp(key->as.s,name)==0) return obj->as.object.items[i+1];
    }
    facoh_raise("NonExistantError", "object attribute does not exist"); return facoh_none();
}
Value *facoh_attr_get_optional(Value *obj, const char *name) {
    if (obj && obj->tag==V_PYOBJECT) { facoh_py_init(); PyObject *value=facoh_lookup_attr((PyObject*)obj->as.py,name); if(!value) return NULL; Value *out=facoh_from_py(value); Py_DECREF(value); return out; }
    if (!obj || obj->tag != V_OBJECT) return NULL;
    for (int64_t i=0;i<obj->as.object.len;i+=2) {
        Value *key=obj->as.object.items[i];
        if (key && key->tag==V_STRING && strcmp(key->as.s,name)==0) return obj->as.object.items[i+1];
    }
    return NULL;
}
void facoh_attr_del(Value *obj, const char *name) {
    if(obj && obj->tag==V_PYOBJECT) { facoh_py_init(); if(PyObject_DelAttrString((PyObject*)obj->as.py,name)<0) facoh_py_error("Python attribute deletion failed"); return; }
    if(!obj || obj->tag!=V_OBJECT) { facoh_raise("TypeError","attribute deletion requires an object"); return; }
    for(int64_t i=0;i+1<obj->as.object.len;i+=2) { Value *key=obj->as.object.items[i]; if(key && key->tag==V_STRING && strcmp(key->as.s,name)==0) { for(int64_t j=i;j+2<obj->as.object.len;j++) obj->as.object.items[j]=obj->as.object.items[j+2]; obj->as.object.len-=2; return; } }
    facoh_raise("NonExistantError","object attribute does not exist");
}
static Value *facoh_builtin_method_call(Value *obj, const char *method, Value **args, int64_t count, const char **kw_names, Value **kw_values, int64_t kw_count) {
    int kind=(obj&&obj->tag==V_STRING)?1:(obj&&obj->tag==V_DICT)?3:((obj&&(obj->tag==V_LIST||obj->tag==V_TUPLE||obj->tag==V_SET))?2:0);
    if(!kind) return NULL;
    if(kind==3 && strcmp(method,"update")==0) {
        if(count>1) { facoh_raise("TypeError","update() accepts at most one positional argument"); return facoh_none(); }
        Value *other=count?args[0]:NULL;
        for(int64_t k=0;k<kw_count;k++) if(strcmp(kw_names[k],"other")==0) { if(other) { facoh_raise("TypeError","update() got multiple values for other"); return facoh_none(); } other=kw_values[k]; }
        if(other && other->tag!=V_NONE) {
            if(other->tag!=V_DICT) { facoh_raise("TypeError","dictionary update requires a dictionary"); return facoh_none(); }
            for(int64_t i=0;i<other->as.list.len;i+=2) facoh_dict_set(obj,other->as.list.items[i],other->as.list.items[i+1]);
        }
        for(int64_t k=0;k<kw_count;k++) if(strcmp(kw_names[k],"other")!=0) facoh_dict_set(obj,facoh_string(kw_names[k]),kw_values[k]);
        return facoh_none();
    }
    const char *names[3]={NULL,NULL,NULL}; Value *defaults[3]={NULL,NULL,NULL}; int64_t arity=0;
    if(kind==1) {
        if(strcmp(method,"upper")==0||strcmp(method,"lower")==0||strcmp(method,"length")==0||strcmp(method,"strip")==0) arity=0;
        else if(strcmp(method,"replace")==0) { names[0]="old"; names[1]="new"; arity=2; }
        else if(strcmp(method,"startswith")==0) { names[0]="prefix"; arity=1; }
        else if(strcmp(method,"endswith")==0) { names[0]="suffix"; arity=1; }
        else if(strcmp(method,"split")==0) { names[0]="separator"; defaults[0]=facoh_none(); arity=1; }
        else { facoh_raise("NonExistantError","string method does not exist"); return facoh_none(); }
    } else if(kind==2) {
        if(strcmp(method,"append")==0) { names[0]="item"; arity=1; }
        else if(strcmp(method,"pop")==0) { names[0]="index"; defaults[0]=facoh_int(-1); arity=1; }
        else if(strcmp(method,"remove")==0) { names[0]="item"; arity=1; }
        else if(strcmp(method,"length")==0||strcmp(method,"reverse")==0||strcmp(method,"sort")==0) arity=0;
        else { facoh_raise("NonExistantError","list method does not exist"); return facoh_none(); }
    } else {
        if(strcmp(method,"keys")==0||strcmp(method,"values")==0||strcmp(method,"length")==0) arity=0;
        else if(strcmp(method,"get")==0) { names[0]="key"; names[1]="default"; defaults[1]=facoh_none(); arity=2; }
        else if(strcmp(method,"update")==0) { names[0]="other"; defaults[0]=facoh_none(); arity=1; }
        else { facoh_raise("NonExistantError","dictionary method does not exist"); return facoh_none(); }
    }
    if(count>arity) { facoh_raise("TypeError","too many method arguments"); return facoh_none(); }
    Value *bound[3]={NULL,NULL,NULL}; for(int64_t i=0;i<count;i++) bound[i]=args[i];
    for(int64_t k=0;k<kw_count;k++) {
        int found=-1; for(int64_t i=0;i<arity;i++) if(names[i]&&strcmp(names[i],kw_names[k])==0) { found=(int)i; break; }
        if(found<0) { facoh_raise("TypeError","unexpected keyword argument for built-in method"); return facoh_none(); }
        if(bound[found]) { facoh_raise("TypeError","multiple values for built-in method argument"); return facoh_none(); }
        bound[found]=kw_values[k];
    }
    for(int64_t i=0;i<arity;i++) if(!bound[i]) bound[i]=defaults[i];
    for(int64_t i=0;i<arity;i++) if(!bound[i]) { facoh_raise("TypeError","missing required method argument"); return facoh_none(); }
    if(kind==1) {
        const char *src=obj->as.s;
        if(strcmp(method,"length")==0) return facoh_int((int64_t)strlen(src));
        if(strcmp(method,"startswith")==0) return facoh_bool(strncmp(src,bound[0]->as.s,strlen(bound[0]->as.s))==0);
        if(strcmp(method,"endswith")==0) { size_t n=strlen(src),m=strlen(bound[0]->as.s); return facoh_bool(m<=n&&strcmp(src+n-m,bound[0]->as.s)==0); }
        if(strcmp(method,"upper")==0||strcmp(method,"lower")==0||strcmp(method,"strip")==0) {
            size_t n=strlen(src); char *buf=(char*)malloc(n+1); if(!buf) exit(1);
            if(strcmp(method,"strip")==0) { const char *a=src; while(*a&&isspace((unsigned char)*a))a++; const char *b=src+strlen(src); while(b>a&&isspace((unsigned char)b[-1]))b--; n=(size_t)(b-a); memcpy(buf,a,n); }
            else { for(size_t i=0;i<n;i++) buf[i]=(char)(strcmp(method,"upper")==0?toupper((unsigned char)src[i]):tolower((unsigned char)src[i])); }
            buf[n]='\0'; Value *out=facoh_string(buf); free(buf); return out;
        }
        if(strcmp(method,"replace")==0) {
            const char *old=bound[0]->as.s,*replacement=bound[1]->as.s; size_t oldn=strlen(old),newn=strlen(replacement),srcn=strlen(src);
            if(oldn==0) { facoh_raise("ValueError","empty separator"); return facoh_none(); }
            size_t capacity=srcn+1; for(const char *p=src;(p=strstr(p,old));p+=oldn) { if(newn>oldn) capacity+=(newn-oldn); else capacity-=(oldn-newn); }
            char *buf=(char*)malloc(capacity+1); if(!buf) exit(1); const char *p=src; char *out=buf;
            while(1) { const char *match=strstr(p,old); if(!match) { size_t rest=strlen(p); memcpy(out,p,rest); out+=rest; break; } size_t chunk=(size_t)(match-p); memcpy(out,p,chunk); out+=chunk; memcpy(out,replacement,newn); out+=newn; p=match+oldn; }
            *out='\0'; Value *result=facoh_string(buf); free(buf); return result;
        }
        if(strcmp(method,"split")==0) {
            Value *out=facoh_list_new(); Value *sep=bound[0];
            if(sep->tag==V_NONE) { const char *p=src; while(*p) { while(*p&&isspace((unsigned char)*p))p++; if(!*p)break; const char *start=p; while(*p&&!isspace((unsigned char)*p))p++; char *part=(char*)malloc((size_t)(p-start)+1); memcpy(part,start,(size_t)(p-start)); part[p-start]='\0'; facoh_list_push(out,facoh_string(part)); free(part); } return out; }
            const char *delimiter=sep->as.s; size_t d=strlen(delimiter); if(!d) { facoh_raise("ValueError","empty separator"); return facoh_none(); }
            const char *p=src; while(1) { const char *match=strstr(p,delimiter); if(!match) { facoh_list_push(out,facoh_string(p)); break; } size_t n=(size_t)(match-p); char *part=(char*)malloc(n+1); memcpy(part,p,n); part[n]='\0'; facoh_list_push(out,facoh_string(part)); free(part); p=match+d; } return out;
        }
    }
    if(kind==2) {
        if(strcmp(method,"length")==0) return facoh_int(obj->as.list.len);
        if(strcmp(method,"append")==0) { facoh_list_push(obj,bound[0]); return facoh_none(); }
        if(strcmp(method,"pop")==0) { int64_t index=facoh_to_i64(bound[0]); int64_t n=obj->as.list.len; if(index<0)index+=n; if(index<0||index>=n) { facoh_raise("IndexError","pop index out of range"); return facoh_none(); } Value *result=obj->as.list.items[index]; for(int64_t i=index;i+1<n;i++)obj->as.list.items[i]=obj->as.list.items[i+1]; obj->as.list.len--; return result; }
        if(strcmp(method,"remove")==0) { int64_t n=obj->as.list.len; for(int64_t i=0;i<n;i++) if(equal_value(obj->as.list.items[i],bound[0])) { for(int64_t j=i;j+1<n;j++)obj->as.list.items[j]=obj->as.list.items[j+1]; obj->as.list.len--; return facoh_none(); } facoh_raise("ValueError","list.remove(x): x not in list"); return facoh_none(); }
        if(strcmp(method,"reverse")==0) { for(int64_t i=0,j=obj->as.list.len-1;i<j;i++,j--) { Value *tmp=obj->as.list.items[i];obj->as.list.items[i]=obj->as.list.items[j];obj->as.list.items[j]=tmp; } return facoh_none(); }
        if(strcmp(method,"sort")==0) { for(int64_t i=1;i<obj->as.list.len;i++) { Value *item=obj->as.list.items[i]; int64_t j=i; while(j>0) { Value *prev=obj->as.list.items[j-1]; int less=0; if(prev->tag==V_STRING&&item->tag==V_STRING) less=strcmp(prev->as.s,item->as.s)>0; else if((prev->tag==V_INT||prev->tag==V_FLOAT||prev->tag==V_BOOL)&&(item->tag==V_INT||item->tag==V_FLOAT||item->tag==V_BOOL)) less=number(prev)>number(item); else { facoh_raise("TypeError","list items are not mutually orderable"); return facoh_none(); } if(!less)break; obj->as.list.items[j]=prev;j--; } obj->as.list.items[j]=item; } return facoh_none(); }
    }
    if(kind==3) {
        if(strcmp(method,"length")==0) return facoh_int(obj->as.list.len/2);
        if(strcmp(method,"keys")==0||strcmp(method,"values")==0) { Value *out=facoh_list_new(); for(int64_t i=0;i<obj->as.list.len;i+=2) facoh_list_push(out,obj->as.list.items[i+(strcmp(method,"values")==0?1:0)]); return out; }
        if(strcmp(method,"get")==0) { for(int64_t i=0;i<obj->as.list.len;i+=2) if(equal_value(obj->as.list.items[i],bound[0]))return obj->as.list.items[i+1]; return bound[1]; }
        if(strcmp(method,"update")==0) { Value *other=bound[0]; if(other->tag==V_NONE)return facoh_none(); if(other->tag!=V_DICT) { facoh_raise("TypeError","dictionary update requires a dictionary"); return facoh_none(); } for(int64_t i=0;i<other->as.list.len;i+=2)facoh_dict_set(obj,other->as.list.items[i],other->as.list.items[i+1]); return facoh_none(); }
    }
    facoh_raise("NonExistantError","built-in method does not exist"); return facoh_none();
}
Value *facoh_method_call(Value *obj, const char *method, Value **args, int64_t count) {
    if(obj && (obj->tag==V_STRING||obj->tag==V_LIST||obj->tag==V_TUPLE||obj->tag==V_SET||obj->tag==V_DICT)) return facoh_builtin_method_call(obj,method,args,count,NULL,NULL,0);
    if(obj && obj->tag==V_PYOBJECT) return facoh_py_method_call(obj,method,args,count,NULL,NULL,0);
    if(!obj || obj->tag!=V_OBJECT) { facoh_raise("TypeError", "method call requires an object"); return facoh_none(); }
    const char *class_name=obj->as.object.name;
    void *target=NULL; int64_t expected_arity=-1;
    for(int depth=0;class_name && class_name[0] && depth<256;depth++) {
        for(int i=facoh_method_count-1;i>=0;i--) {
            if(strcmp(facoh_methods[i].class_name,class_name)==0 && strcmp(facoh_methods[i].method_name,method)==0) { target=facoh_methods[i].function; expected_arity=facoh_methods[i].arity; break; }
        }
        if(target) break;
        class_name=facoh_parent_of(class_name);
    }
    if(!target) { facoh_raise("NonExistantError", "object method does not exist"); return facoh_none(); }
    if(count!=expected_arity) { facoh_raise("TypeError", "incorrect number of method arguments"); return facoh_none(); }
    Value **all=(Value**)malloc((size_t)(count+1)*sizeof(Value*)); if(!all) exit(1);
    all[0]=obj; for(int64_t i=0;i<count;i++) all[i+1]=args[i];
    Value *(*fn)(Value**,int64_t)=(Value *(*)(Value**,int64_t))target;
    Value *result=fn(all,count+1); free(all); return result;
}
Value *facoh_method_call_kw(Value *obj, const char *method, Value **args, int64_t count, const char **kw_names, Value **kw_values, int64_t kw_count) {
    if(obj && (obj->tag==V_STRING||obj->tag==V_LIST||obj->tag==V_TUPLE||obj->tag==V_SET||obj->tag==V_DICT)) return facoh_builtin_method_call(obj,method,args,count,kw_names,kw_values,kw_count);
    if(obj && obj->tag==V_PYOBJECT) return facoh_py_method_call(obj,method,args,count,kw_names,kw_values,kw_count);
    if(kw_count==0) return facoh_method_call(obj,method,args,count);
    if(!obj || obj->tag!=V_OBJECT) { facoh_raise("TypeError","method call requires an object"); return facoh_none(); }
    const char *class_name=obj->as.object.name; FacohMethodEntry *entry=NULL;
    for(int depth=0;class_name && class_name[0] && depth<256;depth++) {
        for(int i=facoh_method_count-1;i>=0;i--) if(strcmp(facoh_methods[i].class_name,class_name)==0 && strcmp(facoh_methods[i].method_name,method)==0) { entry=&facoh_methods[i]; break; }
        if(entry) break; class_name=facoh_parent_of(class_name);
    }
    if(!entry) { facoh_raise("NonExistantError","object method does not exist"); return facoh_none(); }
    if(count>entry->arity) { facoh_raise("TypeError","too many positional method arguments"); return facoh_none(); }
    Value **ordered=(Value**)calloc((size_t)(entry->arity?entry->arity:1),sizeof(Value*)); if(!ordered) exit(1);
    for(int64_t i=0;i<count;i++) ordered[i]=args[i];
    for(int64_t k=0;k<kw_count;k++) {
        int found=-1; for(int64_t i=0;i<entry->arity && i<32;i++) if(strcmp(entry->parameter_names[i],kw_names[k])==0) { found=(int)i; break; }
        if(found<0) { free(ordered); facoh_raise("TypeError","unexpected keyword argument for object method"); return facoh_none(); }
        if(ordered[found]) { free(ordered); facoh_raise("TypeError","multiple values for object method argument"); return facoh_none(); }
        ordered[found]=kw_values[k];
    }
    for(int64_t i=0;i<entry->arity;i++) if(!ordered[i]) { free(ordered); facoh_raise("TypeError","missing required object method argument"); return facoh_none(); }
    Value **all=(Value**)malloc((size_t)(entry->arity+1)*sizeof(Value*)); if(!all) exit(1);
    all[0]=obj; for(int64_t i=0;i<entry->arity;i++) all[i+1]=ordered[i];
    Value *(*fn)(Value**,int64_t)=(Value *(*)(Value**,int64_t))entry->function;
    Value *result=fn(all,entry->arity+1); free(all); free(ordered); return result;
}
Value *facoh_error_value(void) {
    if (facoh_current_error_object) {
        Value *original=facoh_current_error_object;
        facoh_current_error_object=NULL;
        return original;
    }
    Value *v=facoh_object_new(facoh_current_error_type);
    facoh_attr_set(v, "message", facoh_string(facoh_current_error_message));
    return v;
}
static const char *facoh_format_float(double value, char *buffer, size_t size) {
    snprintf(buffer,size,"%.15g",value);
    if (strchr(buffer,'.')==NULL && strchr(buffer,'e')==NULL && strchr(buffer,'E')==NULL && isfinite(value)) {
        size_t n=strlen(buffer); if(n+2<size) { buffer[n]='.'; buffer[n+1]='0'; buffer[n+2]='\0'; }
    }
    return buffer;
}
static const char *facoh_message_text(Value *v, char *buffer, size_t size) {
    if (!v || v->tag==V_NONE) return "None";
    if (v->tag==V_STRING) return v->as.s;
    if (v->tag==V_BOOL) return v->as.b ? "True" : "False";
    if (v->tag==V_INT) { snprintf(buffer,size,"%lld",(long long)v->as.i); return buffer; }
    if (v->tag==V_FLOAT) return facoh_format_float(v->as.f,buffer,size);
    if (v->tag==V_OBJECT) { snprintf(buffer,size,"<%s object>",v->as.object.name?v->as.object.name:"Object"); return buffer; }
    return "thrown value";
}
void facoh_throw_value(Value *v) {
    if (v && v->tag==V_OBJECT) {
        facoh_current_error_object = v;
        const char *name=v->as.object.name ? v->as.object.name : "Error";
        char message_buffer[1024];
        const char *message="";
        for(int64_t i=0;i<v->as.object.len;i+=2) {
            Value *key=v->as.object.items[i];
            if(key && key->tag==V_STRING && strcmp(key->as.s,"message")==0) {
                message=facoh_message_text(v->as.object.items[i+1],message_buffer,sizeof(message_buffer));
            }
        }
        facoh_raise(name,message); return;
    }
    char buffer[1024];
    facoh_raise("Error", facoh_message_text(v,buffer,sizeof(buffer)));
}

typedef struct { void *function; int64_t arity; char name[128]; char parameter_names[32][64]; } FacohNativeFunction;
static PyObject *facoh_native_callback(PyObject *self, PyObject *args, PyObject *kwargs);
static void facoh_native_capsule_free(PyObject *capsule) {
    FacohNativeFunction *ctx=(FacohNativeFunction*)PyCapsule_GetPointer(capsule,"facoh.native_function");
    if(ctx) free(ctx); else PyErr_Clear();
}
static PyMethodDef facoh_native_method_def={"facoh_callback",(PyCFunction)(void(*)(void))facoh_native_callback,METH_VARARGS|METH_KEYWORDS,"Call a FACOH native function."};
static PyObject *facoh_native_callback(PyObject *self, PyObject *args, PyObject *kwargs) {
    FacohNativeFunction *ctx=(FacohNativeFunction*)PyCapsule_GetPointer(self,"facoh.native_function");
    if(!ctx) return NULL;
    Py_ssize_t positional=PyTuple_GET_SIZE(args);
    if(positional>ctx->arity) { PyErr_Format(PyExc_TypeError,"%s() takes %lld argument(s), got %zd",ctx->name,(long long)ctx->arity,positional); return NULL; }
    Value **values=(Value**)calloc((size_t)(ctx->arity?ctx->arity:1),sizeof(Value*)); if(!values) return PyErr_NoMemory();
    for(Py_ssize_t i=0;i<positional;i++) values[i]=facoh_from_py(PyTuple_GET_ITEM(args,i));
    if(kwargs) {
        PyObject *key,*value; Py_ssize_t pos=0;
        while(PyDict_Next(kwargs,&pos,&key,&value)) {
            const char *name=PyUnicode_AsUTF8(key); int found=-1;
            if(name) for(int64_t i=0;i<ctx->arity && i<32;i++) if(strcmp(ctx->parameter_names[i],name)==0) { found=(int)i; break; }
            if(found<0) { free(values); PyErr_Format(PyExc_TypeError,"%s() got an unexpected keyword argument",ctx->name); return NULL; }
            if(values[found]) { free(values); PyErr_Format(PyExc_TypeError,"%s() got multiple values for an argument",ctx->name); return NULL; }
            values[found]=facoh_from_py(value);
        }
    }
    for(int64_t i=0;i<ctx->arity;i++) if(!values[i]) { free(values); PyErr_Format(PyExc_TypeError,"%s() missing required argument '%s'",ctx->name,ctx->parameter_names[i]); return NULL; }
    Value *(*fn)(Value**,int64_t)=(Value *(*)(Value**,int64_t))ctx->function;
    Value *result=fn(values,ctx->arity); free(values);
    return facoh_to_py(result);
}
static int facoh_python_started = 0;
/* Store import paths without starting CPython during native-program setup. */
static char *facoh_pending_python_paths[128];
static int facoh_pending_python_path_count = 0;
static PyObject *facoh_extension_modules[16];
static char facoh_extension_names[16][64];
static int facoh_extension_count = 0;
static PyObject *facoh_python_namespace = NULL;
static char facoh_resource_directory[4096] = "";
static int facoh_threads_may_run = 0;
static int facoh_python_bootstrapped = 0;
static int facoh_defer_bootstrap = 0;
static void facoh_py_bootstrap(void) {
    if(facoh_python_bootstrapped || !facoh_python_namespace) return;
    const char *bootstrap =
        "import builtins, datetime, io, json, math, os, random, re, string, time, struct\n"
        "import threading, multiprocessing\n"
        "globals().update({'openfile': open, 'dis': print, 'takein': input, 'num': int, 'dec': float, 'str': str, 'bool': bool, 'type': type, 'lis': list, 'tup': tuple, 'dic': dict, 'set': set, 'ind': enumerate, 'sorted': sorted, 'reversed': reversed, 'sum': sum, 'min': min, 'max': max, 'abs': abs, 'round': round, 'any': any, 'all': all, 'zip': zip, 'map': map, 'filter': filter, 'isinstance': isinstance, 'issubclass': issubclass, 'super': super, 'getattr': getattr, 'setattr': setattr, 'hasattr': hasattr, 'delattr': delattr, 'iter': iter, 'next': next, 'callable': callable, 'repr': repr, 'hash': hash, 'id': id, 'length': len, 'numste': range, 'wait': time.sleep, 'dat': datetime.datetime, 'dte': datetime.date, 'tme': datetime.time, 'tmedel': datetime.timedelta, 'rn': datetime.datetime.now, 'tdy': datetime.datetime.today, 'frmts': datetime.datetime.fromtimestamp, 'ts': datetime.datetime.timestamp, 'strftime': datetime.datetime.strftime, 'strptime': datetime.datetime.strptime, 'open': io.open, 'StringIO': io.StringIO, 'BytesIO': io.BytesIO, 'turnfch': json.loads, 'turnjson': json.dumps, 'ceil': math.ceil, 'floor': math.floor, 'sqrt': math.sqrt, 'pow': math.pow, 'fabs': math.fabs, 'factorial': math.factorial, 'gcd': math.gcd, 'lcm': math.lcm, 'exp': math.exp, 'log': math.log, 'log10': math.log10, 'sin': math.sin, 'cos': math.cos, 'tan': math.tan, 'asin': math.asin, 'acos': math.acos, 'atan': math.atan, 'degrees': math.degrees, 'radians': math.radians, 'pi': math.pi, 'e': math.e, 'tau': math.tau, 'inf': math.inf, 'nan': math.nan, 'isnan': math.isnan, 'isinf': math.isinf, 'isfinite': math.isfinite, 'comb': math.comb, 'perm': math.perm, 'divmod': divmod, 'getcwd': os.getcwd, 'chdir': os.chdir, 'listdir': os.listdir, 'mkdir': os.mkdir, 'makedirs': os.makedirs, 'remove': os.remove, 'rmdir': os.rmdir, 'rename': os.rename, 'replace': os.replace, 'system': os.system, 'getenv': os.getenv, 'putenv': os.putenv, 'environ': os.environ, 'random': random.random, 'randint': random.randint, 'randrange': random.randrange, 'choice': random.choice, 'choices': random.choices, 'shuffle': random.shuffle, 'sample': random.sample, 'uniform': random.uniform, 'seed': random.seed, 'ascii_letters': string.ascii_letters, 'ascii_lowercase': string.ascii_lowercase, 'ascii_uppercase': string.ascii_uppercase, 'digits': string.digits, 'hexdigits': string.hexdigits, 'octdigits': string.octdigits, 'punctuation': string.punctuation, 'whitespace': string.whitespace, 'search': re.search, 'match': re.match, 'fullmatch': re.fullmatch, 'findall': re.findall, 'finditer': re.finditer, 'split': re.split, 'sub': re.sub, 'subn': re.subn, 'escape': re.escape, 'purge': re.purge})\n";
    PyObject *executed = PyRun_String(bootstrap, Py_file_input, facoh_python_namespace, facoh_python_namespace);
    if (!executed) PyErr_Clear(); else Py_DECREF(executed);
    const char *crypto_bootstrap =
        "import base64, binascii\n"
        "from cryptography.exceptions import InvalidTag\n"
        "from cryptography.hazmat.primitives import hashes\n"
        "from cryptography.hazmat.primitives.ciphers.aead import AESGCM as _AESGCM\n"
        "from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC\n"
        "def _crypto_bytes(value): return value if isinstance(value, bytes) else str(value).encode('utf-8')\n"
        "def _decode_encryption_key(key):\n"
        "    if isinstance(key, bytes): raw_key = key\n"
        "    else:\n"
        "        try: raw_key = base64.urlsafe_b64decode(str(key).encode('ascii'))\n"
        "        except (UnicodeEncodeError, binascii.Error, ValueError) as error: raise ValueError('Key must be generated by generate_key or derive_key') from error\n"
        "    if len(raw_key) not in (16, 24, 32): raise ValueError('AES-GCM keys must be 16, 24, or 32 bytes')\n"
        "    return raw_key\n"
        "def _encrypt_with_key(message, key, associated_data=None):\n"
        "    raw_key = _decode_encryption_key(key); nonce = os.urandom(12)\n"
        "    ciphertext = _AESGCM(raw_key).encrypt(nonce, _crypto_bytes(message), None if associated_data is None else _crypto_bytes(associated_data))\n"
        "    return base64.urlsafe_b64encode(nonce + ciphertext).decode('ascii')\n"
        "def _decrypt_with_key(token, key, associated_data=None):\n"
        "    raw_key = _decode_encryption_key(key)\n"
        "    try: encrypted = base64.b64decode(_crypto_bytes(token), altchars=b'-_', validate=True)\n"
        "    except (binascii.Error, ValueError) as error: raise ValueError('Invalid encrypted token') from error\n"
        "    if len(encrypted) < 28: raise ValueError('Encrypted token is too short')\n"
        "    try: plaintext = _AESGCM(raw_key).decrypt(encrypted[:12], encrypted[12:], None if associated_data is None else _crypto_bytes(associated_data))\n"
        "    except InvalidTag as error: raise ValueError('Authentication failed: wrong key or modified token') from error\n"
        "    try: return plaintext.decode('utf-8')\n"
        "    except UnicodeDecodeError: return plaintext\n"
        "def _generate_key(): return base64.urlsafe_b64encode(os.urandom(32)).decode('ascii')\n"
        "def _derive_key(password, salt=None, iterations=600000):\n"
        "    if not isinstance(iterations, int) or not 100000 <= iterations <= 10000000: raise ValueError('iterations must be between 100000 and 10000000')\n"
        "    if salt is None: raw_salt = os.urandom(16)\n"
        "    elif isinstance(salt, bytes): raw_salt = salt\n"
        "    else:\n"
        "        try: raw_salt = base64.b64decode(_crypto_bytes(salt), altchars=b'-_', validate=True)\n"
        "        except (binascii.Error, ValueError) as error: raise ValueError('salt must be URL-safe base64 from derive_key') from error\n"
        "    if len(raw_salt) < 16: raise ValueError('salt must be at least 16 bytes')\n"
        "    derivation = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=raw_salt, iterations=iterations)\n"
        "    raw_key = derivation.derive(_crypto_bytes(password))\n"
        "    return {'key': base64.urlsafe_b64encode(raw_key).decode('ascii'), 'salt': base64.urlsafe_b64encode(raw_salt).decode('ascii'), 'iterations': iterations}\n"
        "class _FacohAESGCM:\n"
        "    def __init__(self, key=None): self._key = _decode_encryption_key(key) if key is not None else os.urandom(32)\n"
        "    def encrypt(self, message, associated_data=None): return _encrypt_with_key(message, self._key, associated_data)\n"
        "    def decrypt(self, token, associated_data=None): return _decrypt_with_key(token, self._key, associated_data)\n"
        "    def get_key(self): return base64.urlsafe_b64encode(self._key).decode('ascii')\n"
        "globals().update({'AESGCM': _FacohAESGCM, 'generate_key': _generate_key, 'derive_key': _derive_key, 'encrypt': _encrypt_with_key, 'decrypt': _decrypt_with_key})\n";
    PyObject *crypto_executed = PyRun_String(crypto_bootstrap, Py_file_input, facoh_python_namespace, facoh_python_namespace);
    if (!crypto_executed) { PyErr_Clear(); } else Py_DECREF(crypto_executed);
    PyObject *numpy = PyImport_ImportModule("numpy");
    if (numpy) { PyDict_SetItemString(facoh_python_namespace, "fcharrays", numpy); Py_DECREF(numpy); } else PyErr_Clear();
    facoh_python_bootstrapped = 1;
}
static void facoh_py_init(void) {
    if (!facoh_python_started) {
        /* This is the only place that starts CPython. It is reached only by a
           runtime operation that genuinely needs Python, never just to add paths. */
        Py_Initialize();
        facoh_python_started = 1;
        PyObject *sys_path = PySys_GetObject("path");
        if (sys_path) {
            PyObject *cwd = PyUnicode_FromString(".");
            if (cwd) { PyList_Insert(sys_path, 0, cwd); Py_DECREF(cwd); }
            for (int i = 0; i < facoh_pending_python_path_count; ++i) {
                const char *path = facoh_pending_python_paths[i];
                if (!path || !path[0]) continue;
                PyObject *entry = PyUnicode_FromString(path);
                if (entry) {
                    int contains = PySequence_Contains(sys_path, entry);
                    if (contains == 0) PyList_Insert(sys_path, 0, entry);
                    else if (contains < 0) PyErr_Clear();
                    Py_DECREF(entry);
                } else PyErr_Clear();
            }
        }
        for (int i = 0; i < facoh_pending_python_path_count; ++i) {
            free(facoh_pending_python_paths[i]);
            facoh_pending_python_paths[i] = NULL;
        }
        facoh_pending_python_path_count = 0;
        facoh_python_namespace = PyDict_New();
        if (!facoh_python_namespace) { PyErr_Clear(); return; }
        PyDict_SetItemString(facoh_python_namespace, "__builtins__", PyEval_GetBuiltins());
    }
    /* The FACOH namespace (builtins, crypto, numpy) is only read by by-name
       lookups, so it is built lazily by facoh_py_ensure_bootstrap() there.
       Operations on an already-held Python object never need it. */
}
static void facoh_py_ensure_bootstrap(void) { if (!facoh_defer_bootstrap) facoh_py_bootstrap(); }
void facoh_py_begin_configure(void) { facoh_defer_bootstrap=1; }
void facoh_py_finish_configure(void) { facoh_defer_bootstrap=0; }

static Value *facoh_from_py(PyObject *o);
static PyObject *facoh_to_py(Value *v) {
    if (!v || v->tag == V_NONE) { Py_INCREF(Py_None); return Py_None; }
    switch(v->tag) {
        case V_INT: return PyLong_FromLongLong(v->as.i);
        case V_FLOAT: return PyFloat_FromDouble(v->as.f);
        case V_BOOL: return PyBool_FromLong(v->as.b);
        case V_STRING: return PyUnicode_FromString(v->as.s ? v->as.s : "");
        case V_LIST: case V_TUPLE: case V_SET: {
            PyObject *out = v->tag == V_TUPLE ? PyTuple_New((Py_ssize_t)v->as.list.len) : (v->tag == V_SET ? PySet_New(NULL) : PyList_New((Py_ssize_t)v->as.list.len));
            if (!out) return NULL;
            for (int64_t i=0;i<v->as.list.len;i++) {
                PyObject *item = facoh_to_py(v->as.list.items[i]); if (!item) { Py_DECREF(out); return NULL; }
                if (v->tag == V_TUPLE) PyTuple_SET_ITEM(out, (Py_ssize_t)i, item);
                else if (v->tag == V_SET) { if (PySet_Add(out,item)<0) { Py_DECREF(item); Py_DECREF(out); return NULL; } Py_DECREF(item); }
                else PyList_SET_ITEM(out, (Py_ssize_t)i, item);
            }
            return out;
        }
        case V_RANGE: { PyObject *args=Py_BuildValue("(LLL)",(long long)v->as.range.start,(long long)v->as.range.stop,(long long)v->as.range.step); if(!args)return NULL; PyObject *out=PyObject_CallObject((PyObject*)&PyRange_Type,args); Py_DECREF(args); return out; }
        case V_DICT: {
            PyObject *out=PyDict_New(); if(!out) return NULL;
            for(int64_t i=0;i+1<v->as.list.len;i+=2) { PyObject *k=facoh_to_py(v->as.list.items[i]); PyObject *val=facoh_to_py(v->as.list.items[i+1]); if(!k||!val||PyDict_SetItem(out,k,val)<0) { Py_XDECREF(k); Py_XDECREF(val); Py_DECREF(out); return NULL; } Py_DECREF(k); Py_DECREF(val); }
            return out;
        }
        case V_OBJECT: {
            PyObject *out=PyDict_New(); PyObject *name=PyUnicode_FromString(v->as.object.name?v->as.object.name:"Object"); PyObject *attrs=PyDict_New();
            if(!out||!name||!attrs) { Py_XDECREF(out); Py_XDECREF(name); Py_XDECREF(attrs); return NULL; }
            for(int64_t i=0;i+1<v->as.object.len;i+=2) { Value *key=v->as.object.items[i]; if(key&&key->tag==V_STRING) { PyObject *pykey=PyUnicode_FromString(key->as.s); PyObject *pyval=facoh_to_py(v->as.object.items[i+1]); if(!pykey||!pyval||PyDict_SetItem(attrs,pykey,pyval)<0) { Py_XDECREF(pykey); Py_XDECREF(pyval); Py_DECREF(out); Py_DECREF(name); Py_DECREF(attrs); return NULL; } Py_DECREF(pykey); Py_DECREF(pyval); } }
            PyDict_SetItemString(out,"object",name); PyDict_SetItemString(out,"attributes",attrs); Py_DECREF(name); Py_DECREF(attrs); return out;
        }
        case V_PYOBJECT: { PyObject *o=(PyObject*)v->as.py; if(!o) { Py_INCREF(Py_None); return Py_None; } Py_INCREF(o); return o; }
        case V_UNBOUND: Py_INCREF(Py_None); return Py_None;
        default: return PyUnicode_FromString("<FACOH object>");
    }
}
static Value *facoh_py_wrap(PyObject *o) { if(!o) return facoh_none(); Value *v=make_value(V_PYOBJECT); Py_INCREF(o); v->as.py=o; return v; }
static Value *facoh_from_py(PyObject *o) {
    if (!o || o==Py_None) return facoh_none();
    if (PyBool_Check(o)) return facoh_bool(o==Py_True);
    if (PyLong_Check(o)) return facoh_int(PyLong_AsLongLong(o));
    if (PyFloat_Check(o)) return facoh_float(PyFloat_AsDouble(o));
    /* Ordinary extension instances are not numeric. Avoid two failed protocol
       probes (__int__ and __float__) for every constructed object. */
    if (PyNumber_Check(o)) {
        PyObject *l = PyNumber_Long(o);
        if (l) {
            long long val = PyLong_AsLongLong(l);
            Py_DECREF(l);
            if (!PyErr_Occurred()) return facoh_int(val);
            PyErr_Clear();
        } else {
            PyErr_Clear();
        }
        PyObject *f = PyNumber_Float(o);
        if (f) {
            double val = PyFloat_AsDouble(f);
            Py_DECREF(f);
            if (!PyErr_Occurred()) return facoh_float(val);
            PyErr_Clear();
        } else {
            PyErr_Clear();
        }
    }
    if (PyRange_Check(o)) {
        PyObject *start=PyObject_GetAttrString(o,"start"), *stop=PyObject_GetAttrString(o,"stop"), *step=PyObject_GetAttrString(o,"step");
        if(!start||!stop||!step) { Py_XDECREF(start); Py_XDECREF(stop); Py_XDECREF(step); PyErr_Clear(); return facoh_none(); }
        int64_t a=PyLong_AsLongLong(start), b=PyLong_AsLongLong(stop), c=PyLong_AsLongLong(step); Py_DECREF(start); Py_DECREF(stop); Py_DECREF(step);
        Value *v=make_value(V_RANGE); v->as.range.start=a; v->as.range.stop=b; v->as.range.step=c;
        if(c>0) v->as.range.count=a<b?1+(b-1-a)/c:0; else v->as.range.count=a>b?1+(a-1-b)/(-c):0; return v;
    }
    if (PyUnicode_Check(o)) { const char *s=PyUnicode_AsUTF8(o); return facoh_string(s?s:""); }
    if (PyList_Check(o) || PyTuple_Check(o) || PySet_Check(o)) {
        int tag=PyTuple_Check(o)?V_TUPLE:(PySet_Check(o)?V_SET:V_LIST); Value *v=facoh_collection_new(tag);
        PyObject *seq = PySequence_Fast(o,"expected sequence");
        if (seq) { Py_ssize_t n=PySequence_Fast_GET_SIZE(seq); for(Py_ssize_t i=0;i<n;i++) facoh_list_push(v,facoh_from_py(PySequence_Fast_GET_ITEM(seq,i))); Py_DECREF(seq); }
        else PyErr_Clear(); return v;
    }
    if (PyDict_Check(o)) {
        Value *v=facoh_dict_new(); PyObject *key,*val; Py_ssize_t pos=0;
        while(PyDict_Next(o,&pos,&key,&val)) facoh_dict_set(v,facoh_from_py(key),facoh_from_py(val)); return v;
    }
    return facoh_py_wrap(o);
}
static void facoh_py_error(const char *fallback) {
    char message[1024]; char error_type[128]="Error"; snprintf(message,sizeof(message),"%s",fallback?fallback:"Python extension error");
    if (PyErr_Occurred()) {
        PyObject *type=NULL,*value=NULL,*tb=NULL; PyErr_Fetch(&type,&value,&tb); PyErr_NormalizeException(&type,&value,&tb);
        PyObject *text=value?PyObject_Str(value):NULL; if(text) { const char *utf=PyUnicode_AsUTF8(text); if(utf) snprintf(message,sizeof(message),"%s",utf); }
        PyObject *name=type?PyObject_GetAttrString(type,"__name__"):NULL;
        if(name) { const char *utf=PyUnicode_AsUTF8(name); if(utf) { const char *known[]={"SyntaxError","IndexError","ValueError","FileNotFoundError","IndentationError","TypeError","KeyError","TimeoutError","ConnectionError","OSError","ZeroDivisionError"}; for(size_t i=0;i<sizeof(known)/sizeof(known[0]);i++) if(strcmp(utf,known[i])==0) { snprintf(error_type,sizeof(error_type),"%s",utf); break; } } Py_DECREF(name); }
        Py_XDECREF(text); Py_XDECREF(type); Py_XDECREF(value); Py_XDECREF(tb); PyErr_Clear();
    }
    facoh_raise(error_type,message);
}
Value *facoh_native_function(const char *name, void *function, const char **parameter_names, int64_t arity) {
    facoh_py_init();
    FacohNativeFunction *ctx=(FacohNativeFunction*)calloc(1,sizeof(FacohNativeFunction)); if(!ctx) exit(1);
    ctx->function=function; ctx->arity=arity; snprintf(ctx->name,sizeof(ctx->name),"%s",name);
    for(int64_t i=0;i<arity && i<32;i++) snprintf(ctx->parameter_names[i],sizeof(ctx->parameter_names[i]),"%s",parameter_names[i]);
    PyObject *capsule=PyCapsule_New(ctx,"facoh.native_function",facoh_native_capsule_free);
    PyObject *callable=capsule?PyCFunction_NewEx(&facoh_native_method_def,capsule,NULL):NULL; Py_XDECREF(capsule);
    if(!callable) { free(ctx); facoh_py_error("could not create native FACOH callback"); return facoh_none(); }
    Value *out=facoh_py_wrap(callable); Py_DECREF(callable); return out;
}
void facoh_py_add_path(const char *path) {
    if (!path || !path[0]) return;
    /* Native startup config can queue paths without paying CPython startup cost. */
    if (!facoh_python_started) {
        for (int i = 0; i < facoh_pending_python_path_count; ++i)
            if (strcmp(facoh_pending_python_paths[i], path) == 0) return;
        if (facoh_pending_python_path_count < 128) {
            size_t n = strlen(path) + 1;
            char *copy = (char*)malloc(n);
            if (copy) {
                memcpy(copy, path, n);
                facoh_pending_python_paths[facoh_pending_python_path_count++] = copy;
            }
        }
        return;
    }
    PyObject *sys = PyImport_ImportModule("sys");
    if (!sys) { PyErr_Clear(); return; }
    PyObject *paths = PyObject_GetAttrString(sys, "path");
    PyObject *entry = PyUnicode_FromString(path);
    if (paths && entry) {
        int contains = PySequence_Contains(paths, entry);
        if (contains == 0) PyList_Insert(paths, 0, entry);
        else if (contains < 0) PyErr_Clear();
    }
    Py_XDECREF(paths); Py_XDECREF(entry); Py_DECREF(sys);
}
Value *facoh_py_import_module(const char *name) {
    /* Importing a module alone should not force FACOH builtins, crypto, and NumPy bootstrap. */
    int previous_defer=facoh_defer_bootstrap;
    facoh_defer_bootstrap=1;
    facoh_py_init();
    facoh_defer_bootstrap=previous_defer;
    const char *module_name=strcmp(name,"fcharrays")==0?"numpy":name;
    PyObject *module=PyImport_ImportModule(module_name);
    if(!module) { facoh_py_error("could not import Python module"); return facoh_none(); }
    Value *out=facoh_py_wrap(module); Py_DECREF(module); return out;
}
static int facoh_extension_export_conflict(PyObject *module, char *message, size_t message_size) {
    const char *new_maps[]={"FUNCTIONS","OBJECTS"};
    for(int nm=0;nm<2;nm++) {
        PyObject *exports=PyObject_GetAttrString(module,new_maps[nm]);
        if(!exports) { PyErr_Clear(); continue; }
        if(PyDict_Check(exports)) {
            PyObject *key,*value; Py_ssize_t pos=0;
            while(PyDict_Next(exports,&pos,&key,&value)) {
                const char *export_name=PyUnicode_AsUTF8(key); if(!export_name) { PyErr_Clear(); continue; }
                for(int i=0;i<facoh_extension_count;i++) {
                    for(int om=0;om<2;om++) {
                        PyObject *old_exports=PyObject_GetAttrString(facoh_extension_modules[i],new_maps[om]);
                        if(!old_exports) { PyErr_Clear(); continue; }
                        PyObject *existing=PyMapping_GetItemString(old_exports,export_name);
                        Py_DECREF(old_exports);
                        if(existing) {
                            Py_DECREF(existing); snprintf(message,message_size,"Extension %s '%s' conflicts with an existing name",nm==0?"function":"object",export_name); Py_DECREF(exports); return 1;
                        }
                        PyErr_Clear();
                    }
                }
            }
        }
        Py_DECREF(exports);
    }
    return 0;
}
Value *facoh_py_load_extension(const char *name, const char *path) {
    facoh_py_init();
    for(int i=0;i<facoh_extension_count;i++) if(strcmp(facoh_extension_names[i],name)==0) return facoh_py_wrap(facoh_extension_modules[i]);
    PyObject *util=PyImport_ImportModule("importlib.util"); if(!util) { facoh_py_error("could not import importlib.util"); return facoh_none(); }
    PyObject *specfn=PyObject_GetAttrString(util,"spec_from_file_location"); PyObject *modfn=PyObject_GetAttrString(util,"module_from_spec");
    PyObject *pyname=PyUnicode_FromFormat("facoh_extension_%s",name); PyObject *pypath=PyUnicode_FromString(path);
    PyObject *spec=PyObject_CallFunctionObjArgs(specfn,pyname,pypath,NULL); PyObject *module=spec?PyObject_CallFunctionObjArgs(modfn,spec,NULL):NULL;
    PyObject *loader=spec?PyObject_GetAttrString(spec,"loader"):NULL; PyObject *execfn=loader?PyObject_GetAttrString(loader,"exec_module"):NULL;
    PyObject *executed=(module&&execfn)?PyObject_CallFunctionObjArgs(execfn,module,NULL):NULL;
    Py_XDECREF(executed); Py_XDECREF(execfn); Py_XDECREF(loader); Py_XDECREF(spec); Py_DECREF(util); Py_DECREF(specfn); Py_DECREF(modfn); Py_DECREF(pyname); Py_DECREF(pypath);
    if(!module || PyErr_Occurred()) { Py_XDECREF(module); facoh_py_error("failed loading FACOH extension"); return facoh_none(); }
    char conflict[512];
    if(facoh_extension_export_conflict(module,conflict,sizeof(conflict))) { Py_DECREF(module); PyErr_SetString(PyExc_ValueError,conflict); facoh_py_error("extension export conflict"); return facoh_none(); }
    if(facoh_extension_count<16) { snprintf(facoh_extension_names[facoh_extension_count],64,"%s",name); facoh_extension_modules[facoh_extension_count++]=module; }
    return facoh_py_wrap(module);
}
static PyObject *facoh_py_find_callable(const char *name) {
    char name_buf[512];
    snprintf(name_buf, sizeof(name_buf), "%s", name);
    char *dot = strchr(name_buf, '.');
    if (dot) {
        *dot = '\0';
        char *mod_name = name_buf;
        char *attr_name = dot + 1;
        PyObject *obj = facoh_py_find_callable(mod_name);
        if (!obj) return NULL;
        PyObject *attr = facoh_lookup_attr(obj, attr_name);
        if (!attr) {
            PyErr_Clear();
            const char *maps[] = {"FUNCTIONS", "OBJECTS"};
            for(int m=0; m<2; m++) {
                PyObject *exports = facoh_lookup_attr(obj, maps[m]);
                if(exports) {
                    attr = facoh_mapping_get(exports, attr_name);
                    Py_DECREF(exports);
                    if(attr) break;
                    PyErr_Clear();
                } else {
                    PyErr_Clear();
                }
            }
        }
        Py_DECREF(obj);
        if (!attr) { PyErr_Clear(); return NULL; }
        return attr;
    }
    for(int i=0;i<facoh_extension_count;i++) {
        PyObject *module=facoh_extension_modules[i];
        const char *maps[]={"FUNCTIONS","OBJECTS"};
        for(int m=0; m<2; m++) { PyObject *exports=facoh_lookup_attr(module,maps[m]); if(exports) { PyObject *item=facoh_mapping_get(exports,name); Py_DECREF(exports); if(item) return item; PyErr_Clear(); } else PyErr_Clear(); }
        PyObject *item=facoh_lookup_attr(module,name); if(item) return item; PyErr_Clear();
    }
    facoh_py_ensure_bootstrap();
    if(facoh_python_namespace) { PyObject *item=PyDict_GetItemString(facoh_python_namespace,name); if(item) { Py_INCREF(item); return item; } }
    PyObject *builtins=PyEval_GetBuiltins(); PyObject *item=PyDict_GetItemString(builtins,name); if(item) { Py_INCREF(item); return item; }
    return NULL;
}
Value *facoh_py_get_global(const char *name) {
    facoh_py_init();
    for(int i=0;i<facoh_extension_count;i++) {
        PyObject *module=facoh_extension_modules[i];
        PyObject *item=facoh_lookup_attr(module,name);
        if(item) return facoh_from_py(item);
        PyErr_Clear();
        const char *maps[]={"FUNCTIONS","OBJECTS"};
        for(int m=0;m<2;m++) { PyObject *exports=facoh_lookup_attr(module,maps[m]); if(exports) { item=facoh_mapping_get(exports,name); Py_DECREF(exports); if(item) return facoh_from_py(item); PyErr_Clear(); } else PyErr_Clear(); }
    }
    facoh_py_ensure_bootstrap();
    if(facoh_python_namespace) { PyObject *item=PyDict_GetItemString(facoh_python_namespace,name); if(item) return facoh_from_py(item); }
    char message[512]; snprintf(message,sizeof(message),"undefined FACOH name: %s",name); facoh_raise("NonExistantError",message); return facoh_none();
}
static PyObject *facoh_py_build_args(Value **args, int64_t count) {
    PyObject *tuple=PyTuple_New((Py_ssize_t)count); if(!tuple) return NULL;
    for(int64_t i=0;i<count;i++) { PyObject *item=facoh_to_py(args[i]); if(!item) { Py_DECREF(tuple); return NULL; } PyTuple_SET_ITEM(tuple,(Py_ssize_t)i,item); }
    return tuple;
}
static PyObject *facoh_py_vectorcall(Value *callable, Value **args, int64_t count) {
    if (!callable || callable->tag != V_PYOBJECT || !PyCallable_Check((PyObject*)callable->as.py)) {
        PyErr_SetString(PyExc_TypeError, "value is not callable");
        return NULL;
    }
    if (count < 0) { PyErr_SetString(PyExc_ValueError, "negative argument count"); return NULL; }
    PyObject *local_args[8];
    PyObject **argv = count <= 8 ? local_args : (PyObject**)malloc((size_t)count * sizeof(PyObject*));
    if (!argv) { PyErr_NoMemory(); return NULL; }
    int64_t made = 0;
    for (; made < count; ++made) {
        argv[made] = facoh_to_py(args[made]);
        if (!argv[made]) {
            for (int64_t j = 0; j < made; ++j) Py_DECREF(argv[j]);
            if (argv != local_args) free(argv);
            return NULL;
        }
    }
    PyObject *result = PyObject_Vectorcall((PyObject*)callable->as.py, argv, (size_t)count, NULL);
    for (int64_t j = 0; j < made; ++j) Py_DECREF(argv[j]);
    if (argv != local_args) free(argv);
    return result;
}
static PyObject *facoh_py_build_kwargs(const char **names, Value **values, int64_t count) {
    if(!count) return NULL;
    PyObject *dict=PyDict_New(); if(!dict) return NULL;
    for(int64_t i=0;i<count;i++) { PyObject *key=PyUnicode_FromString(names[i]); PyObject *val=facoh_to_py(values[i]); if(!key||!val||PyDict_SetItem(dict,key,val)<0) { Py_XDECREF(key); Py_XDECREF(val); Py_DECREF(dict); return NULL; } Py_DECREF(key); Py_DECREF(val); }
    return dict;
}
Value *facoh_py_call_value(Value *callable, Value **args, int64_t count, const char **kw_names, Value **kw_values, int64_t kw_count) {
    facoh_py_init();
    if(!callable || callable->tag!=V_PYOBJECT || !PyCallable_Check((PyObject*)callable->as.py)) { facoh_raise("TypeError","value is not callable"); return facoh_none(); }
    PyObject *result = NULL;
    if (kw_count == 0) {
        result = facoh_py_vectorcall(callable, args, count);
    } else {
        PyObject *tuple=facoh_py_build_args(args,count); PyObject *kwargs=facoh_py_build_kwargs(kw_names,kw_values,kw_count);
        result=tuple?PyObject_Call((PyObject*)callable->as.py,tuple,kwargs):NULL; Py_XDECREF(tuple); Py_XDECREF(kwargs);
    }
    if(!result || PyErr_Occurred()) { Py_XDECREF(result); facoh_py_error("callable invocation failed"); return facoh_none(); }
    Value *out=facoh_from_py(result); Py_DECREF(result); return out;
}
void facoh_py_set_resource_directory(const char *path) { snprintf(facoh_resource_directory,sizeof(facoh_resource_directory),"%s",path?path:""); }
Value *facoh_py_call(const char *name, Value **args, int64_t count, const char **kw_names, Value **kw_values, int64_t kw_count) {
    facoh_py_init(); PyObject *fn=facoh_py_find_callable(name);
    if(!fn) { char msg[512]; snprintf(msg,sizeof(msg),"unknown FACOH/Python function: %s",name); facoh_raise("NonExistantError",msg); return facoh_none(); }
    PyObject *tuple = NULL;
    PyObject *kwargs = NULL;
    PyObject *result = NULL;
    if (kw_count == 0 && !(strcmp(name,"UI")==0 && facoh_resource_directory[0])) {
        Value callable_value = {0}; callable_value.tag = V_PYOBJECT; callable_value.as.py = fn;
        result = facoh_py_vectorcall(&callable_value, args, count);
    } else {
        tuple=facoh_py_build_args(args,count); kwargs=kw_count?facoh_py_build_kwargs(kw_names,kw_values,kw_count):NULL;
    }
    if(strcmp(name,"UI")==0 && facoh_resource_directory[0]) {
        if(!kwargs) kwargs=PyDict_New();
        if(kwargs && !PyDict_GetItemString(kwargs,"resource_directory")) { PyObject *path=PyUnicode_FromString(facoh_resource_directory); if(path) { PyDict_SetItemString(kwargs,"resource_directory",path); Py_DECREF(path); } }
    }
    if (!result && tuple) result=PyObject_Call(fn,tuple,kwargs); Py_XDECREF(tuple); Py_XDECREF(kwargs); Py_DECREF(fn);
    if(!result || PyErr_Occurred()) { Py_XDECREF(result); facoh_py_error("Python call failed"); return facoh_none(); }
    if(strcmp(name,"host")==0 || strcmp(name,"udp_host")==0 || strcmp(name,"start_server")==0) facoh_threads_may_run=1;
    Value *out=facoh_from_py(result); Py_DECREF(result); return out;
}
Value *facoh_py_method_call(Value *obj, const char *method, Value **args, int64_t count, const char **kw_names, Value **kw_values, int64_t kw_count) {
    if(!obj || obj->tag!=V_PYOBJECT) { if(kw_count) return facoh_method_call_kw(obj,method,args,count,kw_names,kw_values,kw_count); return facoh_method_call(obj,method,args,count); }
    facoh_py_init(); 
    PyObject *py_obj = (PyObject*)obj->as.py;
    PyObject *fn = facoh_lookup_attr(py_obj, method); 
    if(!fn) { 
        const char *maps[] = {"FUNCTIONS", "OBJECTS"};
        for(int m=0; m<2; m++) {
            PyObject *exports = facoh_lookup_attr(py_obj, maps[m]);
            if(exports) {
                fn = facoh_mapping_get(exports, method);
                Py_DECREF(exports);
                if(fn) break;
                PyErr_Clear();
            } else {
                PyErr_Clear();
            }
        }
    }
    if(!fn) { facoh_py_error("Python method does not exist"); return facoh_none(); }
    PyObject *tuple=facoh_py_build_args(args,count); PyObject *kwargs=kw_count?facoh_py_build_kwargs(kw_names,kw_values,kw_count):NULL;
    PyObject *result=tuple?PyObject_Call(fn,tuple,kwargs):NULL; Py_XDECREF(tuple); Py_XDECREF(kwargs); Py_DECREF(fn);
    if(!result || PyErr_Occurred()) { Py_XDECREF(result); facoh_py_error("Python method call failed"); return facoh_none(); }
    if(strcmp(method,"start")==0 || strcmp(method,"host")==0 || strcmp(method,"udp_host")==0 || strcmp(method,"acquire")==0 || strcmp(method,"start_server")==0) facoh_threads_may_run=1;
    Value *out=facoh_from_py(result); Py_DECREF(result); return out;
}

void facoh_py_yield(void) {
    if(!facoh_python_started || !facoh_threads_may_run) return;
    PyThreadState *state=PyEval_SaveThread();
#ifdef _WIN32
    SwitchToThread();
#else
    sched_yield();
#endif
    PyEval_RestoreThread(state);
}
Value *facoh_py_stringify(Value *value) { facoh_py_init(); PyObject *obj=facoh_to_py(value); if(!obj) { facoh_py_error("string conversion failed"); return facoh_none(); } PyObject *text=PyObject_Str(obj); Py_DECREF(obj); if(!text) { facoh_py_error("string conversion failed"); return facoh_none(); } Value *out=facoh_from_py(text); Py_DECREF(text); return out; }
Value *facoh_context_enter(Value *context) {
    if(!context || context->tag!=V_PYOBJECT) { facoh_raise("TypeError","fileoc expression is not a Python context manager"); return facoh_none(); }
    facoh_py_init(); PyObject *result=PyObject_CallMethod((PyObject*)context->as.py,"__enter__",NULL);
    if(!result) { facoh_py_error("fileoc __enter__ failed"); return facoh_none(); }
    Value *out=facoh_from_py(result); Py_DECREF(result); return out;
}
int32_t facoh_context_exit_error(Value *context) {
    if(!context || context->tag!=V_PYOBJECT) return 0;
    facoh_py_init(); PyObject *type=PyExc_Exception;
    if(strcmp(facoh_current_error_type,"ValueError")==0) type=PyExc_ValueError;
    else if(strcmp(facoh_current_error_type,"TypeError")==0) type=PyExc_TypeError;
    else if(strcmp(facoh_current_error_type,"ZeroDivisionError")==0) type=PyExc_ZeroDivisionError;
    else if(strcmp(facoh_current_error_type,"IndexError")==0) type=PyExc_IndexError;
    else if(strcmp(facoh_current_error_type,"KeyError")==0) type=PyExc_KeyError;
    else if(strcmp(facoh_current_error_type,"FileNotFoundError")==0) type=PyExc_FileNotFoundError;
    else if(strcmp(facoh_current_error_type,"OSError")==0) type=PyExc_OSError;
    PyObject *value=PyObject_CallFunction(type,"s",facoh_current_error_message);
    PyObject *result=value?PyObject_CallMethod((PyObject*)context->as.py,"__exit__","OOO",type,value,Py_None):NULL;
    Py_XDECREF(value);
    if(!result) { facoh_py_error("fileoc __exit__ failed while handling an exception"); return 0; }
    int suppressed=PyObject_IsTrue(result); Py_DECREF(result);
    if(suppressed>0) { facoh_current_error_type[0]='\0'; facoh_current_error_message[0]='\0'; facoh_current_error_object=NULL; return 1; }
    if(suppressed<0) { facoh_py_error("fileoc __exit__ truth test failed"); return 0; }
    return 0;
}
Value *facoh_context_exit(Value *context) {
    if(!context || context->tag!=V_PYOBJECT) return facoh_none();
    facoh_py_init(); PyObject *result=PyObject_CallMethod((PyObject*)context->as.py,"__exit__","OOO",Py_None,Py_None,Py_None);
    if(!result) { facoh_py_error("fileoc __exit__ failed"); return facoh_none(); }
    Value *out=facoh_from_py(result); Py_DECREF(result); return out;
}
Value *facoh_dict_new(void) { return make_value(V_DICT); }
Value *facoh_list_get(Value *v, int64_t i);
int64_t facoh_to_i64(Value *v);
void facoh_dict_set(Value *v, Value *key, Value *item) {
    if (!v || v->tag != V_DICT) { facoh_raise("TypeError", "expected dictionary"); }
    for (int64_t i=0;i<v->as.list.len;i+=2) { if (equal_value(v->as.list.items[i], key)) { v->as.list.items[i+1]=item; return; } }
    if (v->as.list.len + 2 > v->as.list.cap) { int64_t cap=v->as.list.cap?v->as.list.cap*2:8; while(cap<v->as.list.len+2) cap*=2; Value **p=(Value**)realloc(v->as.list.items,(size_t)cap*sizeof(Value*)); if(!p) exit(1); v->as.list.items=p; v->as.list.cap=cap; }
    v->as.list.items[v->as.list.len++]=key; v->as.list.items[v->as.list.len++]=item;
}
Value *facoh_get_item(Value *v, Value *key) {
    if(v && v->tag==V_RANGE) return facoh_list_get(v,facoh_to_i64(key));
    if(v && v->tag==V_PYOBJECT) { facoh_py_init(); PyObject *pykey=facoh_to_py(key); PyObject *item=pykey?PyObject_GetItem((PyObject*)v->as.py,pykey):NULL; Py_XDECREF(pykey); if(!item) { facoh_py_error("Python object indexing failed"); return facoh_none(); } Value *out=facoh_from_py(item); Py_DECREF(item); return out; }
    if (v && v->tag==V_DICT) { for(int64_t i=0;i<v->as.list.len;i+=2) if(equal_value(v->as.list.items[i],key)) return v->as.list.items[i+1]; facoh_raise("KeyError", "dictionary key not found"); }
    return facoh_list_get(v, facoh_to_i64(key));
}
int64_t facoh_list_len(Value *v) {
    if (!v) return 0;
    if (v->tag==V_RANGE) return v->as.range.count;
    if (v->tag == V_LIST || v->tag == V_TUPLE || v->tag == V_SET) return v->as.list.len;
    if (v->tag == V_DICT) return v->as.list.len/2;
    if (v->tag == V_STRING) return (int64_t)strlen(v->as.s);
    if (v->tag==V_PYOBJECT) { facoh_py_init(); Py_ssize_t n=PyObject_Length((PyObject*)v->as.py); if(n<0) { PyErr_Clear(); facoh_raise("TypeError", "Python value has no length"); } return (int64_t)n; }
    facoh_raise("TypeError", "value is not iterable");
}
Value *facoh_list_get(Value *v, int64_t i) {
    if(v && v->tag==V_RANGE) { int64_t n=v->as.range.count; if(i<0)i+=n; if(i<0||i>=n) { facoh_raise("IndexError","range index out of range"); return facoh_none(); } return facoh_int(v->as.range.start+i*v->as.range.step); }
    if(v && v->tag==V_PYOBJECT) { facoh_py_init(); PyObject *item=PySequence_GetItem((PyObject*)v->as.py,(Py_ssize_t)i); if(!item) { facoh_py_error("Python sequence index out of range"); return facoh_none(); } Value *out=facoh_from_py(item); Py_DECREF(item); return out; }
    if (!v) { facoh_raise("TypeError", "null value"); }
    if (v->tag == V_DICT) { int64_t n=v->as.list.len/2; if(i<0) i+=n; if(i<0||i>=n) { facoh_raise("IndexError", "dictionary iteration index out of range"); } return v->as.list.items[i*2]; }
    if (v->tag == V_LIST || v->tag == V_TUPLE || v->tag == V_SET) {
        if (i < 0) i += v->as.list.len;
        if (i < 0 || i >= v->as.list.len) { facoh_raise("IndexError", "array index out of range"); }
        return v->as.list.items[i];
    }
    if (v->tag == V_STRING) {
        int64_t n=(int64_t)strlen(v->as.s); if(i<0) i+=n;
        if(i<0 || i>=n) { facoh_raise("IndexError", "string index out of range"); }
        char tmp[2]={v->as.s[i],0}; return facoh_string(tmp);
    }
    facoh_raise("TypeError", "value cannot be indexed");
}
Value *facoh_iter_new(Value *source) {
    Value *v=make_value(V_ITERATOR);
    if(source && source->tag==V_PYOBJECT) { facoh_py_init(); v->as.iter.iterator=PyObject_GetIter((PyObject*)source->as.py); if(!v->as.iter.iterator) { facoh_py_error("value is not iterable"); return facoh_none(); } }
    else { if(!source || !(source->tag==V_LIST || source->tag==V_TUPLE || source->tag==V_SET || source->tag==V_DICT || source->tag==V_STRING || source->tag==V_RANGE)) { facoh_raise("TypeError","value is not iterable"); return facoh_none(); } v->as.iter.source=source; v->as.iter.index=0; }
    return v;
}
int32_t facoh_iter_has_next(Value *iterator) {
    if(!iterator || iterator->tag!=V_ITERATOR) { facoh_raise("TypeError","invalid iterator"); return 0; }
    if(iterator->as.iter.done) return 0;
    if(iterator->as.iter.iterator) {
        if(iterator->as.iter.pending) return 1;
        facoh_py_init(); PyObject *item=PyIter_Next(iterator->as.iter.iterator);
        if(!item) { if(PyErr_Occurred()) facoh_py_error("iteration failed"); iterator->as.iter.done=1; return 0; }
        iterator->as.iter.pending=facoh_from_py(item); Py_DECREF(item); return 1;
    }
    return iterator->as.iter.index<facoh_list_len(iterator->as.iter.source);
}
Value *facoh_iter_next(Value *iterator) {
    if(!iterator || iterator->tag!=V_ITERATOR) { facoh_raise("TypeError","invalid iterator"); return facoh_none(); }
    if(iterator->as.iter.iterator) {
        if(!iterator->as.iter.pending && !facoh_iter_has_next(iterator)) { facoh_raise("IndexError","iterator is exhausted"); return facoh_none(); }
        Value *item=iterator->as.iter.pending; iterator->as.iter.pending=NULL; return item;
    }
    Value *source = iterator->as.iter.source;
    if(source && source->tag == V_RANGE) {
        int64_t idx = iterator->as.iter.index++;
        int64_t n = source->as.range.count;
        if(idx < 0 || idx >= n) { facoh_raise("IndexError","range index out of range"); return facoh_none(); }
        Value *val = iterator->as.iter.pending;
        if(!val) {
            val = make_value(V_INT);
            iterator->as.iter.pending = val;
        }
        val->tag = V_INT;
        val->as.i = source->as.range.start + idx * source->as.range.step;
        return val;
    }
    return facoh_list_get(source,iterator->as.iter.index++);
}
Value *facoh_slice(Value *v, int64_t start, int64_t end) {
    if (v && v->tag==V_STRING) {
        int64_t n=(int64_t)strlen(v->as.s);
        if(start<0) start+=n; if(end<0) end+=n;
        if(start<0) start=0; if(start>n) start=n;
        if(end<0) end=0; if(end>n) end=n;
        if(end<start) end=start;
        size_t count=(size_t)(end-start);
        char *part=(char*)malloc(count+1); if(!part) exit(1);
        memcpy(part,v->as.s+start,count); part[count]='\0';
        Value *result=facoh_string(part); free(part); return result;
    }
    if (!v || (v->tag!=V_LIST && v->tag!=V_TUPLE && v->tag!=V_SET)) {
        facoh_raise("TypeError", "slicing requires a string or collection");
    }
    int64_t n=v->as.list.len;
    if(start<0) start+=n; if(end<0) end+=n;
    if(start<0) start=0; if(start>n) start=n;
    if(end<0) end=0; if(end>n) end=n;
    if(end<start) end=start;
    Value *result=facoh_list_new();
    for(int64_t i=start;i<end;i++) facoh_list_push(result,v->as.list.items[i]);
    return result;
}
static inline double number(Value *v) {
    if (!v) return 0;
    if (v->tag==V_INT) return (double)v->as.i;
    if (v->tag==V_FLOAT) return v->as.f;
    if (v->tag==V_BOOL) return v->as.b;
    facoh_raise("TypeError", "numeric operation needs numbers");
}

static inline int truth(Value *v) {
    if (!v || v->tag==V_NONE) return 0;
    if (v->tag==V_BOOL) return v->as.b;
    if (v->tag==V_INT) return v->as.i!=0;
    if (v->tag==V_FLOAT) return v->as.f!=0.0;
    if (v->tag==V_STRING) return v->as.s[0]!=0;
    if (v->tag==V_LIST || v->tag==V_TUPLE || v->tag==V_SET) return v->as.list.len!=0;
    if (v->tag==V_DICT) return v->as.list.len!=0;
    if (v->tag==V_RANGE) return v->as.range.count!=0;
    if (v->tag==V_PYOBJECT) { facoh_py_init(); int result=PyObject_IsTrue((PyObject*)v->as.py); if(result<0) { PyErr_Clear(); return 0; } return result; }
    return 1;
}
int32_t facoh_truthy(Value *v) { return truth(v); }
int64_t facoh_to_i64(Value *v) { if (!v) return 0; if(v->tag==V_INT) return v->as.i; if(v->tag==V_BOOL) return v->as.b; if(v->tag==V_FLOAT) return (int64_t)v->as.f; facoh_raise("TypeError", "expected a number for index/range"); }
static int equal_value(Value *a, Value *b) {
    if (!a || !b) return a==b;
    if ((a->tag==V_INT || a->tag==V_FLOAT || a->tag==V_BOOL) && (b->tag==V_INT || b->tag==V_FLOAT || b->tag==V_BOOL)) return number(a)==number(b);
    if (a->tag!=b->tag) return 0;
    if (a->tag==V_STRING) return strcmp(a->as.s,b->as.s)==0;
    if (a->tag==V_NONE) return 1;
    return a==b;
}
Value *facoh_unary(int op, Value *a) {
    if(a && a->tag==V_PYOBJECT) { facoh_py_init(); PyObject *obj=facoh_to_py(a); PyObject *result=NULL; if(op==1) result=PyNumber_Negative(obj); else if(op==2) result=PyBool_FromLong(!PyObject_IsTrue(obj)); Py_XDECREF(obj); if(!result) { facoh_py_error("Python unary operator failed"); return facoh_none(); } Value *out=facoh_from_py(result); Py_DECREF(result); return out; }
    if(op==1) return a && a->tag==V_FLOAT ? facoh_float(-a->as.f) : facoh_int(-(int64_t)number(a));
    if(op==2) return facoh_bool(!truth(a));
    facoh_raise("TypeError", "unsupported unary operator");
}
Value *facoh_binary(int op, Value *a, Value *b) {
    if((a && a->tag==V_PYOBJECT) || (b && b->tag==V_PYOBJECT)) {
        facoh_py_init(); PyObject *left=facoh_to_py(a), *right=facoh_to_py(b), *result=NULL;
        if(!left || !right) { Py_XDECREF(left); Py_XDECREF(right); facoh_py_error("could not convert operands for Python operator"); return facoh_none(); }
        switch(op) {
            case 1: result=PyNumber_Add(left,right); break; case 2: result=PyNumber_Subtract(left,right); break;
            case 3: result=PyNumber_Multiply(left,right); break; case 4: result=PyNumber_TrueDivide(left,right); break;
            case 5: result=PyNumber_Power(left,right,Py_None); break; case 6: result=PyNumber_Remainder(left,right); break;
            case 10: result=PyBool_FromLong(PyObject_IsTrue(left) && PyObject_IsTrue(right)); break;
            case 11: result=PyBool_FromLong(PyObject_IsTrue(left) || PyObject_IsTrue(right)); break;
            case 12: result=PyBool_FromLong(PySequence_Contains(right,left)); break;
            case 13: result=PyObject_RichCompare(left,right,Py_NE); break; case 14: result=PyObject_RichCompare(left,right,Py_EQ); break;
            case 15: result=PyBool_FromLong(left==right); break; case 16: result=PyBool_FromLong(left!=right); break;
            case 17: { int contains=PySequence_Contains(right,left); result=PyBool_FromLong(contains==0); break; }
            case 20: result=PyObject_RichCompare(left,right,Py_LT); break; case 21: result=PyObject_RichCompare(left,right,Py_GT); break;
            case 22: result=PyObject_RichCompare(left,right,Py_LE); break; case 23: result=PyObject_RichCompare(left,right,Py_GE); break;
            default: break;
        }
        Py_DECREF(left); Py_DECREF(right); if(!result || PyErr_Occurred()) { Py_XDECREF(result); facoh_py_error("Python binary operator failed"); return facoh_none(); }
        Value *out=facoh_from_py(result); Py_DECREF(result); return out;
    }
    if(op==10) return facoh_bool(truth(a) && truth(b));
    if(op==11) return facoh_bool(truth(a) || truth(b));
    if(op==12) {
        if(b && (b->tag==V_LIST || b->tag==V_TUPLE || b->tag==V_SET)) { for(int64_t i=0;i<b->as.list.len;i++) if(equal_value(a,b->as.list.items[i])) return facoh_bool(1); return facoh_bool(0); }
        if(b && b->tag==V_DICT) { for(int64_t i=0;i<b->as.list.len;i+=2) if(equal_value(a,b->as.list.items[i])) return facoh_bool(1); return facoh_bool(0); }
        if(a && a->tag==V_STRING && b && b->tag==V_STRING) return facoh_bool(strstr(b->as.s,a->as.s)!=NULL);
        facoh_raise("TypeError", "'in' needs an array or string");
    }
    if(op==13) return facoh_bool(!equal_value(a,b));
    if(op==14) return facoh_bool(equal_value(a,b));
    if(op==15) return facoh_bool(a==b);
    if(op==16) return facoh_bool(a!=b);
    if(op==17) { Value *r=facoh_binary(12,a,b); return facoh_bool(!truth(r)); }
    if(op>=20 && op<=23) {
        if(a && b && a->tag==V_STRING && b->tag==V_STRING) { int c=strcmp(a->as.s,b->as.s); return facoh_bool(op==20?c<0:op==21?c>0:op==22?c<=0:c>=0); }
        double x=number(a), y=number(b); return facoh_bool(op==20?x<y:op==21?x>y:op==22?x<=y:x>=y);
    }
    if(op==1 && a && b && a->tag==V_STRING && b->tag==V_STRING) { size_t n=strlen(a->as.s)+strlen(b->as.s)+1; char *s=(char*)malloc(n); if(!s) exit(1); strcpy(s,a->as.s); strcat(s,b->as.s); Value *v=facoh_string(s); free(s); return v; }
    if(op==1 && a && b && a->tag==V_LIST && b->tag==V_LIST) { Value *v=facoh_list_new(); for(int64_t i=0;i<a->as.list.len;i++) facoh_list_push(v,a->as.list.items[i]); for(int64_t i=0;i<b->as.list.len;i++) facoh_list_push(v,b->as.list.items[i]); return v; }
    if(op==4) { double x=number(a), y=number(b); if(y==0) { facoh_raise("ZeroDivisionError", "Cannot divide by zero"); } return facoh_float(x/y); }
    if((a && a->tag==V_FLOAT) || (b && b->tag==V_FLOAT) || op==5) {
        double x=number(a), y=number(b);
        if(op==1) return facoh_float(x+y); if(op==2) return facoh_float(x-y); if(op==3) return facoh_float(x*y);
        if(op==5) return facoh_float(pow(x,y));
        if(op==6) { if(y==0) { facoh_raise("ZeroDivisionError", "Cannot divide by zero"); } return facoh_float(fmod(x,y)); }
    }
    int64_t x=(int64_t)number(a), y=(int64_t)number(b);
    if(op==1) return facoh_int(x+y); if(op==2) return facoh_int(x-y); if(op==3) return facoh_int(x*y);
    if(op==5) { if(y<0) return facoh_float(pow((double)x,(double)y)); int64_t r=1; while(y) { if(y&1) r*=x; y>>=1; if(y) x*=x; } return facoh_int(r); }
    if(op==6) { if(y==0) { facoh_raise("ZeroDivisionError", "Cannot divide by zero"); } return facoh_int(x%y); }
    facoh_raise("TypeError", "unsupported binary operator");
}
Value *facoh_range(int64_t start, int64_t stop, int64_t step) {
    if(step==0) { facoh_raise("ValueError","range() arg 3 must not be zero"); return facoh_none(); }
    Value *v=make_value(V_RANGE); v->as.range.start=start; v->as.range.stop=stop; v->as.range.step=step;
    if(step>0) v->as.range.count=start<stop?1+(stop-1-start)/step:0;
    else v->as.range.count=start>stop?1+(start-1-stop)/(-step):0;
    return v;
}
static void print_value(Value *v, int nested) {
    if(!v) { fputs("None",stdout); return; }
    switch(v->tag) {
        case V_INT: printf("%lld",(long long)v->as.i); break;
        case V_FLOAT: { char buffer[128]; fputs(facoh_format_float(v->as.f,buffer,sizeof(buffer)),stdout); break; }
        case V_BOOL: fputs(v->as.b?"True":"False",stdout); break;
        case V_STRING: if(nested) printf("'%s'",v->as.s); else fputs(v->as.s,stdout); break;
        case V_NONE: fputs("None",stdout); break;
        case V_RANGE: if(v->as.range.step==1) printf("range(%lld, %lld)",(long long)v->as.range.start,(long long)v->as.range.stop); else printf("range(%lld, %lld, %lld)",(long long)v->as.range.start,(long long)v->as.range.stop,(long long)v->as.range.step); break;
        case V_LIST: case V_TUPLE: case V_SET: case V_DICT: {
            char open='[', close=']';
            if(v->tag==V_DICT || v->tag==V_SET){open='{';close='}';}
            if(v->tag==V_TUPLE){open='(';close=')';}
            if(v->tag==V_SET && v->as.list.len==0){fputs("set()",stdout);break;}
            putchar(open);
            int64_t count=v->tag==V_DICT?v->as.list.len/2:v->as.list.len;
            for(int64_t i=0;i<count;i++){
                if(i) fputs(", ",stdout);
                if(v->tag==V_DICT){
                    print_value(v->as.list.items[i*2],1);
                    fputs(": ",stdout);
                    print_value(v->as.list.items[i*2+1],1);
                } else print_value(v->as.list.items[i],1);
            }
            if(v->tag==V_TUPLE && count==1) fputc(',',stdout);
            putchar(close); break;
        }
        case V_OBJECT: printf("<%s object>", v->as.object.name ? v->as.object.name : "Object"); break;
        case V_PYOBJECT: { facoh_py_init(); PyObject *text=PyObject_Str((PyObject*)v->as.py); if(text) { const char *utf=PyUnicode_AsUTF8(text); fputs(utf?utf:"<Python object>",stdout); Py_DECREF(text); } else { PyErr_Clear(); fputs("<Python object>",stdout); } break; }
        default: fputs("<value>",stdout);
    }
}
void facoh_print(Value *v) { print_value(v,0); putchar('\n'); fflush(stdout); }
void facoh_print_many(Value **values, int64_t count) {
    for (int64_t i=0;i<count;i++) {
        if (i) putchar(' ');
        print_value(values[i],0);
    }
    putchar('\n');
    fflush(stdout);
}
'''

_BINARY_OPS = {
    "+": 1, "-": 2, "*": 3, "/": 4, "**": 5, "%": 6,
    "also": 10, "and": 10, "or": 11, "in": 12, "!in": 17,
    "!=": 13, "not in": 17, "=": 14, "==": 14, "is": 15, "!is": 16, "is not": 16,
    "<": 20, ">": 21, "<=": 22, ">=": 23,
}


class Compiler:
    def __init__(self, contents, filename="<module>"):
        self.contents = contents
        self.filename = Path(filename).resolve(
        ) if filename != "<module>" else Path.cwd() / "<module>"
        self.lexer = Lexer(contents, "Interpreter")
        self.module = ir.Module(name="facoh")
        self.builder = None
        self.variables = {}
        self.global_variables = {}
        self.functions = {}
        self.loop_stack = []
        self.string_counter = 0
        self.object_nodes = {}
        self.method_nodes = {}
        self.object_context = None
        self.object_parameter_names = set()
        self.finally_stack = []
        self.handler_stack = []
        self.uses_python_runtime = False
        self.needs_thread_yield = False

    def compile(self, output_path):
        tokens = self.lexer.lex()
        self.parser = Parser(tokens, "Interpreter", self.contents)
        self.ast, self.diagnostics = self.parser.parse_program()
        if self.diagnostics:
            messages = [
                f"{diagnostic.type} at line {diagnostic.line}, "
                f"column {diagnostic.column}: {diagnostic.message}"
                for diagnostic in self.diagnostics
            ]
            raise SyntaxError("\n".join(messages))

        self.ast = self._expand_fch_imports(self.ast, self.filename, set())
        self.ast = self._remove_unused_extension_imports(self.ast)
        self.module = ir.Module(name="facoh")
        self.string_counter = 0
        self._declare_runtime()
        self._collect_functions_and_globals()
        self.uses_python_runtime = self._ast_needs_python(self.ast)
        self.needs_thread_yield = self._ast_needs_thread_yield(self.ast)
        self._declare_user_functions()
        self._compile_user_functions()
        self._compile_method_functions()
        self._compile_main()

        ir_path = None
        runtime_path = None
        runtime_object = None
        try:
            # Optimize LLVM IR in-memory using llvmlite.binding pass manager
            try:
                mod_ref = llvm.parse_assembly(str(self.module))
                mod_ref.verify()
                pmb = llvm.PassManagerBuilder()
                pmb.opt_level = 3  # Prioritize runtime speed over compile time
                pmb.size_level = 0
                pmb.inliner = llvm.create_function_inlining_pass(30)
                pmb.loop_vectorize = True
                pmb.slp_vectorize = True
                pm = llvm.ModulePassManager()
                pmb.populate(pm)
                pm.run(mod_ref)
                optimized_ir_str = str(mod_ref)
            except Exception:  # noqa: BLE001
                optimized_ir_str = str(self.module)

            with tempfile.NamedTemporaryFile(mode="w", suffix=".ll", encoding="utf-8", delete=False) as f:
                f.write(optimized_ir_str)
                ir_path = Path(f.name)

            portable_build = os.environ.get("FACOH_PORTABLE_BUILD", "").strip().lower() in {
                "1", "true", "yes"}
            machine = platform.machine().lower()
            cpu_flags = []
            if not portable_build:
                if machine in {"x86_64", "amd64", "i386", "i686"}:
                    cpu_flags = ["-march=native", "-mtune=native"]
                elif machine in {"aarch64", "arm64"}:
                    cpu_flags = ["-mcpu=native"]
            optimization_flags = ["-O3", "-fno-strict-aliasing",
                                  "-fomit-frame-pointer", "-fno-math-errno", *cpu_flags]
            try:
                clang_version = subprocess.run(
                    ["clang", "--version"], check=True, capture_output=True, text=True
                ).stdout.splitlines()[0]
            except (OSError, subprocess.CalledProcessError, IndexError):
                clang_version = "clang-unknown"
            cache_key = hashlib.sha256((
                RUNTIME_C + sys.version +
                str(sysconfig.get_config_var("SOABI"))
                + os.name + sys.platform +
                str(sysconfig.get_config_var("LIBRARY"))
                + clang_version + " ".join(optimization_flags)
            ).encode("utf-8")).hexdigest()[:24]
            cache_dir = Path(tempfile.gettempdir()) / \
                "facoh_native_runtime_cache"
            cache_dir.mkdir(parents=True, exist_ok=True)
            runtime_object = cache_dir / \
                (f"runtime_{cache_key}.obj" if os.name ==
                 "nt" else f"runtime_{cache_key}.o")
            if not runtime_object.exists():
                with tempfile.NamedTemporaryFile(mode="w", suffix=".c", encoding="utf-8", delete=False) as f:
                    f.write(RUNTIME_C)
                    runtime_path = Path(f.name)
                object_command = ["clang", *optimization_flags,
                                  "-Wno-deprecated-declarations"]
                include_dir = sysconfig.get_path("include")
                if include_dir:
                    object_command.extend(["-I", include_dir])
                object_command.extend(
                    ["-c", str(runtime_path), "-o", str(runtime_object)])
                try:
                    subprocess.run(object_command, check=True)
                except Exception:
                    runtime_object.unlink(missing_ok=True)
                    raise
            command = ["clang", *optimization_flags, "-Wno-override-module",
                       str(ir_path), str(runtime_object), "-o", str(output_path)]
            if os.name == "nt":
                library = sysconfig.get_config_var(
                    "LIBRARY") or sysconfig.get_config_var("LDLIBRARY")
                py_version = f"python{sys.version_info.major}{sys.version_info.minor}"
                library_names = []
                for name in (library, f"{py_version}.lib", "python3.lib"):
                    if name:
                        name = Path(name).name
                        if name not in library_names:
                            library_names.append(name)
                candidate_dirs = []
                for raw_dir in (
                    sysconfig.get_config_var("LIBDIR"),
                    sysconfig.get_config_var("LIBPL"),
                    str(Path(sys.base_prefix) / "libs"),
                    str(Path(sys.exec_prefix) / "libs"),
                    str(Path(sys.base_prefix) / "Libs"),
                ):
                    if raw_dir:
                        candidate = Path(raw_dir)
                        if candidate not in candidate_dirs:
                            candidate_dirs.append(candidate)
                found_library = None
                for directory in candidate_dirs:
                    for name in library_names:
                        candidate = directory / name
                        if candidate.is_file():
                            found_library = candidate.resolve()
                            break
                    if found_library:
                        break
                for directory in candidate_dirs:
                    if directory.is_dir():
                        command.extend(["-L", str(directory)])
                if found_library:
                    command.append(str(found_library))
                else:
                    searched = ", ".join(str(d) for d in candidate_dirs)
                    raise RuntimeError(
                        f"Cannot find the Python import library ({', '.join(library_names)}). "
                        f"Searched: {searched}."
                    )
            else:
                libdir = sysconfig.get_config_var("LIBDIR")
                ldlib = sysconfig.get_config_var("LDLIBRARY") or ""
                if libdir:
                    command.extend(["-L", libdir])
                libname = ldlib.removeprefix("lib")
                for suffix in (".so", ".a", ".dylib"):
                    libname = libname.removesuffix(suffix)
                if libname:
                    command.append("-l" + libname)
                command.extend(["-ldl", "-lm"])
            subprocess.run(command, check=True)
            print(f"Compiled successfully: {output_path}")
        finally:
            if ir_path is not None:
                ir_path.unlink(missing_ok=True)
            if runtime_path is not None:
                runtime_path.unlink(missing_ok=True)

    def _allocate_temp_array(self, count):
        if count <= 0:
            return ir.Constant(self.pv.as_pointer(), None), None
        bytes_needed = self._const_i64(count * 8)
        raw_ptr = self.builder.call(self.runtime["malloc"], [bytes_needed])
        casted_ptr = self.builder.bitcast(raw_ptr, self.pv.as_pointer())
        return casted_ptr, raw_ptr

    def _free_temp_array(self, raw_ptr):
        if raw_ptr is not None:
            self.builder.call(self.runtime["free"], [raw_ptr])

    def _declare_runtime(self):
        i1 = ir.IntType(1)  # noqa: F841
        i8 = ir.IntType(8)
        i32 = ir.IntType(32)
        i64 = ir.IntType(64)
        f64 = ir.DoubleType()
        p8 = i8.as_pointer()
        pv = p8
        self.pv = pv
        self.i8 = i8
        self.i32 = i32
        self.i64 = i64
        self.f64 = f64
        self.runtime = {}

        def declare(name, result, args):
            fn = ir.Function(self.module, ir.FunctionType(
                result, args), name=name)
            self.runtime[name] = fn
            return fn

        declare("facoh_int", pv, [i64])
        declare("facoh_float", pv, [f64])
        declare("facoh_bool", pv, [i32])
        declare("facoh_string", pv, [p8])
        declare("facoh_none", pv, [])
        declare("facoh_unbound", pv, [])
        declare("facoh_check_defined", pv, [pv, p8])
        declare("facoh_unary", pv, [i32, pv])
        declare("facoh_binary", pv, [i32, pv, pv])
        declare("malloc", p8, [i64])
        declare("free", ir.VoidType(), [p8])
        declare("facoh_truthy", i32, [pv])
        declare("facoh_to_i64", i64, [pv])
        declare("facoh_print", ir.VoidType(), [pv])
        declare("facoh_print_many", ir.VoidType(), [pv.as_pointer(), i64])
        declare("facoh_list_new", pv, [])
        declare("facoh_tuple_new", pv, [])
        declare("facoh_collection_new", pv, [i32])
        declare("facoh_dict_new", pv, [])
        declare("facoh_dict_set", ir.VoidType(), [pv, pv, pv])
        declare("facoh_get_item", pv, [pv, pv])
        declare("facoh_slice", pv, [pv, i64, i64])
        declare("facoh_list_push", ir.VoidType(), [pv, pv])
        declare("facoh_list_get", pv, [pv, i64])
        declare("facoh_iter_new", pv, [pv])
        declare("facoh_iter_has_next", i32, [pv])
        declare("facoh_iter_next", pv, [pv])
        declare("facoh_list_len", i64, [pv])
        declare("facoh_range", pv, [i64, i64, i64])
        declare("facoh_handler_get", p8, [])
        declare("facoh_handler_set", ir.VoidType(), [p8])
        declare("facoh_error_matches", i32, [p8])
        declare("facoh_error_value", pv, [])
        declare("facoh_throw_value", ir.VoidType(), [pv])
        declare("facoh_object_new", pv, [p8])
        declare("facoh_attr_set", ir.VoidType(), [pv, p8, pv])
        declare("facoh_attr_del", ir.VoidType(), [pv, p8])
        declare("facoh_attr_get", pv, [pv, p8])
        declare("facoh_attr_get_optional", pv, [pv, p8])
        declare("facoh_register_object", ir.VoidType(), [p8, p8])
        declare("facoh_register_method", ir.VoidType(),
                [p8, p8, p8, i64, p8.as_pointer(), i64])
        declare("facoh_method_call", pv, [pv, p8, pv.as_pointer(), i64])
        declare("facoh_method_call_kw", pv, [
                pv, p8, pv.as_pointer(), i64, p8.as_pointer(), pv.as_pointer(), i64])
        declare("facoh_py_load_extension", pv, [p8, p8])
        declare("facoh_py_import_module", pv, [p8])
        declare("facoh_py_add_path", ir.VoidType(), [p8])
        declare("facoh_py_begin_configure", ir.VoidType(), [])
        declare("facoh_py_finish_configure", ir.VoidType(), [])
        declare("facoh_py_set_resource_directory", ir.VoidType(), [p8])
        declare("facoh_native_function", pv, [p8, p8, p8.as_pointer(), i64])
        declare("facoh_py_get_global", pv, [p8])
        declare("facoh_context_enter", pv, [pv])
        declare("facoh_py_stringify", pv, [pv])
        declare("facoh_py_yield", ir.VoidType(), [])
        declare("facoh_context_exit", pv, [pv])
        declare("facoh_context_exit_error", i32, [pv])
        declare("facoh_py_call", pv, [p8, pv.as_pointer(
        ), i64, p8.as_pointer(), pv.as_pointer(), i64])
        declare("facoh_py_call_value", pv, [
                pv, pv.as_pointer(), i64, p8.as_pointer(), pv.as_pointer(), i64])
        declare("facoh_py_method_call", pv, [
                pv, p8, pv.as_pointer(), i64, p8.as_pointer(), pv.as_pointer(), i64])
        self.setjmp_name = "_setjmp" if os.name == "nt" else "setjmp"
        if os.name == "nt":
            self.frameaddress = ir.Function(
                self.module,
                ir.FunctionType(p8, [i32]),
                name="llvm.frameaddress.p0i8",
            )
            setjmp_args = [p8, p8]
        else:
            setjmp_args = [p8]
        setjmp_fn = declare(self.setjmp_name, i32, setjmp_args)
        setjmp_fn.attributes.add("returns_twice")
        declare("facoh_rethrow", ir.VoidType(), [])

    def _resolve_import_path(self, module_name, importer):
        base = Path(importer).resolve().parent
        path = (base / module_name).resolve()
        if path.suffix == "":
            if path.exists():
                pass
            elif Path(str(path) + ".fch").exists():
                path = Path(str(path) + ".fch")
            else:
                path = Path(str(path) + ".fch")
        if path.suffix != ".fch":
            raise ValueError(
                f"FACOH imports must reference .fch files: {module_name}")
        if not path.exists():
            raise FileNotFoundError(f"FACOH module not found: {path}")
        return path

    def _parse_imported_fch(self, path):
        contents = path.read_text(encoding="utf-8")
        tokens = Lexer(contents, "Interpreter").lex()
        parser = Parser(tokens, "Interpreter", contents)
        nodes, diagnostics = parser.parse_program()
        if diagnostics:
            raise SyntaxError(
                f"Could not parse imported FACOH module {path}: {diagnostics[0].message}")
        return nodes

    def _expand_fch_imports(self, nodes, importer, stack):
        imported_definitions = []
        processed = []
        known = {}

        def load_module(module_name, requested_name, alias, current_importer):
            path = self._resolve_import_path(module_name, current_importer)
            if path in stack:
                raise ValueError(
                    f"Circular FACOH module import involving '{path.name}'")
            module_nodes = self._parse_imported_fch(path)
            stack.add(path)
            try:
                nested = []
                for item in module_nodes:
                    if item.get("type") == "use":
                        child_name = item.get("name")
                        child_from = item.get("from")
                        if child_from is None and child_name in {"ui", "lan", "web_api", "web_ui", "db", "graphics", "threading", "multiprocessing", "fcharrays"}:
                            continue
                        child_module = child_from if child_from is not None else child_name
                        nested.extend(load_module(
                            child_module, child_name if child_from is not None else None, item.get("var"), path))
                definitions = {
                    item["name"]: item for item in module_nodes if item.get("type") == "Obj"}
                if requested_name is None:
                    selected = list(definitions.values())
                else:
                    if requested_name not in definitions:
                        raise NameError(
                            f"Object '{requested_name}' does not exist in '{module_name}'")
                    selected = []
                    visited = set()

                    def include(name):
                        if name in visited:
                            return
                        visited.add(name)
                        definition = definitions[name]
                        parent = definition.get("parent")
                        if parent in definitions:
                            include(parent)
                        selected.append(definition)
                    include(requested_name)
                clones = []
                for definition in selected:
                    clone = dict(definition)
                    if alias and requested_name is not None and definition["name"] == requested_name:
                        clone["name"] = alias
                    clone["_import_source"] = str(path)
                    clones.append(clone)
                return nested + clones
            finally:
                stack.remove(path)
        for node in nodes:
            if node.get("type") != "use":
                processed.append(node)
                continue
            name = node.get("name")
            from_name = node.get("from")
            if from_name is None and name in {"ui", "lan", "web_api", "web_ui", "db", "graphics", "threading", "multiprocessing", "fcharrays"}:
                processed.append(node)
                continue
            module_name = from_name if from_name is not None else name
            imported = load_module(
                module_name, name if from_name is not None else None, node.get("var"), importer)
            for definition in imported:
                key = definition["name"]
                if key not in known:
                    known[key] = definition
                    imported_definitions.append(definition)
            processed.append({"type": "pass"})
        return processed + imported_definitions

    def _ast_needs_thread_yield(self, value):
        if isinstance(value, list):
            return any(self._ast_needs_thread_yield(item) for item in value)
        if not isinstance(value, dict):
            return False
        if value.get("type") == "use" and value.get("name") in {"lan", "web_api", "db", "threading", "multiprocessing"}:
            return True
        return any(self._ast_needs_thread_yield(child) for child in value.values())

    def _remove_unused_extension_imports(self, nodes):
        """Remove built-in extension imports whose module binding is unused."""
        extension_names = {"ui", "lan", "web_api",
                           "web_ui", "db", "graphics", "fcharrays"}
        referenced = set()

        def collect(value):
            if isinstance(value, list):
                for item in value:
                    collect(item)
                return
            if not isinstance(value, dict):
                return
            if value.get("type") == "Variable":
                referenced.add(value.get("name"))
            for child in value.values():
                collect(child)

        collect(nodes)
        kept = []
        for node in nodes:
            if node.get("type") == "use" and node.get("from") is None:
                module_name = node.get("name")
                binding = node.get("var") or module_name
                if module_name in extension_names and binding not in referenced:
                    continue
            kept.append(node)
        return kept

    def _ast_needs_python(self, value):
        if isinstance(value, list):
            return any(self._ast_needs_python(item) for item in value)
        if not isinstance(value, dict):
            return False
        kind = value.get("type")
        if kind in {"use", "fileoc", "fstring"}:
            return True
        if kind == "Variable" and value.get("name") in self.function_nodes:
            return True
        if kind == "Call":
            name = value.get("name")
            native = {"dis", "length", "numste"}
            errors = {"Error", "SyntaxError", "IndexError", "ValueError", "NonExistantError", "ZeroDivisionError",
                      "FileNotFoundError", "IndentationError", "TypeError", "KeyError", "TimeoutError", "ConnectionError", "OSError"}
            if name not in native and name not in errors and name not in self.function_nodes and name not in self.object_nodes:
                return True
        return any(self._ast_needs_python(child) for child in value.values())

    def _collect_functions_and_globals(self):
        self.function_nodes = {}
        self.object_nodes = {}
        self.method_nodes = {}
        global_names = set()
        for node in self.ast:
            if node["type"] == "Obj":
                self.object_nodes[node["name"]] = node
                for method in node["methods"]:
                    key = f"{node['name']}__{method['name']}"
                    self.method_nodes[key] = {
                        **method, "owner": node["name"], "key": key}
            elif node["type"] == "Function":
                name = node["name"]
                if name in self.function_nodes or name == "dis":
                    raise SyntaxError(
                        f"Duplicate or reserved function name: {name}")
                self.function_nodes[name] = node
            else:
                global_names.update(self._assigned_names(node))
        for name in sorted(global_names):
            glob = ir.GlobalVariable(
                self.module, self.pv, name=f"facoh_global_{name}")
            glob.initializer = ir.Constant(self.pv, None)
            self.global_variables[name] = glob

    def _assigned_names(self, node):
        found = set()
        if not isinstance(node, dict):
            return found
        kind = node.get("type")
        if kind == "Function":
            return found
        if kind == "Assignment":
            found.add(node["name"])
        elif kind == "For":
            found.add(node["variable"])
        for key in ("block", "else_block", "finally_block"):
            child = node.get(key)
            if isinstance(child, list):
                for item in child:
                    found.update(self._assigned_names(item))
        for caught in node.get("caughts", {}).values():
            if caught.get("var"):
                found.add(caught["var"])
            found.update(self._assigned_names(
                {"type": "Block", "block": caught.get("block", [])}))
        return found

    def _declare_user_functions(self):
        function_type = ir.FunctionType(
            self.pv, [self.pv.as_pointer(), self.i64])
        for name in self.function_nodes:
            self.functions[name] = ir.Function(
                self.module, function_type, name=f"facoh_fn_{name}")
        for key in self.method_nodes:
            self.functions[key] = ir.Function(
                self.module, function_type, name=f"facoh_method_{key}")

    def _local_names(self, nodes):
        names = set()
        for node in nodes:
            if not isinstance(node, dict) or node.get("type") == "Function":
                continue
            if node.get("type") == "Assignment":
                names.add(node["name"])
            if node.get("type") == "For":
                names.add(node["variable"])
            for key in ("block", "else_block", "finally_block"):
                child = node.get(key)
                if isinstance(child, list):
                    names.update(self._local_names(child))
            for caught in node.get("caughts", {}).values():
                if caught.get("var"):
                    names.add(caught["var"])
                names.update(self._local_names(caught.get("block", [])))
        return names

    def _new_entry_alloca(self, name, value_type=None):
        return self.builder.alloca(value_type or self.pv, name=f"slot_{name}")

    def _compile_user_functions(self):
        for name, node in self.function_nodes.items():
            fn = self.functions[name]
            entry = fn.append_basic_block("entry")
            self.builder = ir.IRBuilder(entry)
            self.variables = {}
            self.loop_stack = []
            self.finally_stack = []
            self.handler_stack = []
            params = node["parameters"]
            all_names = self._local_names(node["block"]) | set(params)
            for local_name in sorted(all_names):
                self.variables[local_name] = self._new_entry_alloca(local_name)
            args_ptr = fn.args[0]
            for index, param in enumerate(params):
                slot = self.variables[param]
                arg_ptr = self.builder.gep(args_ptr, [self._const_i64(index)])
                arg_value = self.builder.load(arg_ptr, name=f"arg_{param}")
                self.builder.store(arg_value, slot)
            self._compile_block(node["block"])
            if not self.builder.block.is_terminated:
                self.builder.ret(self.builder.call(
                    self.runtime["facoh_none"], []))

    def _compile_method_functions(self):
        for key, node in self.method_nodes.items():
            fn = self.functions[key]
            entry = fn.append_basic_block("entry")
            self.builder = ir.IRBuilder(entry)
            self.variables = {}
            self.loop_stack = []
            self.finally_stack = []
            self.handler_stack = []
            args_ptr = fn.args[0]
            self.object_context = self.builder.load(self.builder.gep(
                args_ptr, [self._const_i64(0)]), name="this_object")
            self.object_parameter_names = set(node["parameters"])
            for index, param in enumerate(node["parameters"], start=1):
                slot = self._new_entry_alloca(param)
                self.variables[param] = slot
                arg_ptr = self.builder.gep(args_ptr, [self._const_i64(index)])
                arg_value = self.builder.load(arg_ptr, name=f"arg_{param}")
                self.builder.store(arg_value, slot)
            self._compile_block(node["block"])
            if not self.builder.block.is_terminated:
                self.builder.ret(self.builder.call(
                    self.runtime["facoh_none"], []))
            self.object_context = None
            self.object_parameter_names = set()

    def _object_lineage_nodes(self, name):
        lineage = []
        visited = set()
        while name and name in self.object_nodes and name not in visited:
            visited.add(name)
            node = self.object_nodes[name]
            lineage.append(node)
            name = node.get("parent")
        builtin_errors = {"Error", "SyntaxError", "IndexError", "ValueError", "NonExistantError", "ZeroDivisionError",
                          "FileNotFoundError", "IndentationError", "TypeError", "KeyError", "TimeoutError", "ConnectionError", "OSError"}
        if name and name not in visited and name not in self.object_nodes and name not in builtin_errors:
            raise NameError(f"Unknown parent object: {name}")
        return list(reversed(lineage))

    def _compile_main(self):
        main = ir.Function(self.module, ir.FunctionType(
            self.i32, []), name="main")
        entry = main.append_basic_block("entry")
        self.builder = ir.IRBuilder(entry)
        self.variables = {}
        self.loop_stack = []
        self.finally_stack = []
        self.handler_stack = []
        for glob in self.global_variables.values():
            self.builder.store(self.builder.call(
                self.runtime["facoh_none"], []), glob)
        self.builder.call(self.runtime["facoh_register_object"], [
                          self._string_ptr("Error"), self._string_ptr("")])
        for error_name in ("SyntaxError", "IndexError", "ValueError", "NonExistantError", "ZeroDivisionError", "FileNotFoundError", "IndentationError", "TypeError", "KeyError", "TimeoutError", "ConnectionError", "OSError"):
            self.builder.call(self.runtime["facoh_register_object"], [
                              self._string_ptr(error_name), self._string_ptr("Error")])
        for object_name, object_node in self.object_nodes.items():
            parent = object_node.get("parent") or ""
            self.builder.call(self.runtime["facoh_register_object"], [
                              self._string_ptr(object_name), self._string_ptr(parent)])
        for key, method_node in self.method_nodes.items():
            fn_ptr = self.builder.bitcast(self.functions[key], self.pv)
            params = method_node["parameters"]
            if params:
                params_type = ir.ArrayType(self.i8.as_pointer(), len(params))
                params_array = self.builder.alloca(
                    params_type, name=f"method_param_names_{key}")
                for index, param in enumerate(params):
                    ptr = self.builder.gep(
                        params_array, [self._const_i32(0), self._const_i32(index)])
                    self.builder.store(self._string_ptr(param), ptr)
                params_ptr = self.builder.gep(
                    params_array, [self._const_i32(0), self._const_i32(0)])
            else:
                params_ptr = ir.Constant(
                    self.i8.as_pointer().as_pointer(), None)
            self.builder.call(self.runtime["facoh_register_method"], [self._string_ptr(method_node["owner"]), self._string_ptr(
                method_node["name"]), fn_ptr, self._const_i64(len(params)), params_ptr, self._const_i64(len(params))])
        if self.uses_python_runtime:
            self.builder.call(self.runtime["facoh_py_set_resource_directory"], [
                              self._string_ptr(str(self.filename.parent.resolve()))])
            self.builder.call(self.runtime["facoh_py_begin_configure"], [])
            python_paths = []
            for entry in sys.path:
                if entry:
                    path = str(Path(entry).resolve())
                    if path not in python_paths and Path(path).exists():
                        python_paths.append(path)
            project_root = str(Path(__file__).resolve().parent)
            if project_root not in python_paths:
                python_paths.insert(0, project_root)
            for path in python_paths:
                self.builder.call(self.runtime["facoh_py_add_path"], [
                                  self._string_ptr(path)])
            self.builder.call(self.runtime["facoh_py_finish_configure"], [])
        for node in self.ast:
            if node["type"] not in ("Function", "Obj"):
                self.compile_statement(node)
                if self.needs_thread_yield and not self.builder.block.is_terminated:
                    self.builder.call(self.runtime["facoh_py_yield"], [])
                if self.builder.block.is_terminated:
                    break
        if not self.builder.block.is_terminated:
            self.builder.ret(ir.Constant(self.i32, 0))

    def _const_i32(self, value):
        return ir.Constant(self.i32, value)

    def _const_i64(self, value):
        return ir.Constant(self.i64, value)

    def _string_ptr(self, value):
        raw = value.encode("utf-8") + b"\0"
        arr_ty = ir.ArrayType(ir.IntType(8), len(raw))
        name = f".facoh_str_{self.string_counter}"
        self.string_counter += 1
        glob = ir.GlobalVariable(self.module, arr_ty, name=name)
        glob.global_constant = True
        glob.linkage = "internal"
        glob.initializer = ir.Constant(arr_ty, bytearray(raw))
        zero = ir.Constant(self.i32, 0)
        return self.builder.gep(glob, [zero, zero], inbounds=True)

    def _slot_for(self, name, create=False):
        if name in self.variables:
            return self.variables[name]
        if name in self.global_variables:
            return self.global_variables[name]
        if create and self.builder.function.name == "main":
            glob = ir.GlobalVariable(
                self.module, self.pv, name=f"facoh_global_{name}")
            glob.initializer = ir.Constant(self.pv, None)
            self.builder.store(self.builder.call(
                self.runtime["facoh_none"], []), glob)
            self.global_variables[name] = glob
            return glob
        if create:
            slot = self._new_entry_alloca(name)
            self.variables[name] = slot
            self.builder.store(self.builder.call(
                self.runtime["facoh_none"], []), slot)
            return slot
        raise NameError(f"Undefined variable: {name}")

    def compile_expression(self, node):
        if node is None:
            return self.builder.call(self.runtime["facoh_none"], [])
        node_type = node["type"]
        if node_type == "literal":
            raw = node["value"]
            try:
                value = ast.literal_eval(raw)
            except (ValueError, SyntaxError):
                if raw == "true":
                    value = True
                elif raw == "false":
                    value = False
                elif raw == "inf":
                    value = float("inf")
                elif raw == "-inf":
                    value = float("-inf")
                elif raw == "nan":
                    value = float("nan")
                else:
                    raise NotImplementedError(f"Unsupported literal: {raw!r}")
            if isinstance(value, bool):
                return self.builder.call(self.runtime["facoh_bool"], [self._const_i32(int(value))])
            if isinstance(value, int):
                return self.builder.call(self.runtime["facoh_int"], [self._const_i64(value)])
            if isinstance(value, float):
                return self.builder.call(self.runtime["facoh_float"], [ir.Constant(self.f64, value)])
            if isinstance(value, str):
                return self.builder.call(self.runtime["facoh_string"], [self._string_ptr(value)])
            raise NotImplementedError(
                f"Unsupported literal type: {type(value).__name__}")

        if node_type == "Variable":
            if node["name"] in self.function_nodes:
                self.uses_python_runtime = True
                parameters = self.function_nodes[node["name"]]["parameters"]
                if parameters:
                    params_type = ir.ArrayType(
                        self.i8.as_pointer(), len(parameters))
                    params_array = self.builder.alloca(
                        params_type, name=f"callback_params_{node['name']}")
                    for index, param in enumerate(parameters):
                        ptr = self.builder.gep(
                            params_array, [self._const_i32(0), self._const_i32(index)])
                        self.builder.store(self._string_ptr(param), ptr)
                    params_ptr = self.builder.gep(
                        params_array, [self._const_i32(0), self._const_i32(0)])
                else:
                    params_ptr = ir.Constant(
                        self.i8.as_pointer().as_pointer(), None)
                fn_ptr = self.builder.bitcast(
                    self.functions[node["name"]], self.pv)
                return self.builder.call(self.runtime["facoh_native_function"], [self._string_ptr(node["name"]), fn_ptr, params_ptr, self._const_i64(len(parameters))])
            if self.object_context is not None and node["name"] not in self.variables:
                attribute = self.builder.call(self.runtime["facoh_attr_get_optional"], [
                                              self.object_context, self._string_ptr(node["name"])])
                if node["name"] in self.global_variables:
                    fallback = self.builder.load(
                        self.global_variables[node["name"]])
                    exists = self.builder.icmp_unsigned(
                        "!=", attribute, ir.Constant(self.pv, None))
                    return self.builder.select(exists, attribute, fallback)
                return self.builder.call(self.runtime["facoh_attr_get"], [self.object_context, self._string_ptr(node["name"])])
            try:
                slot = self._slot_for(node["name"])
            except NameError:
                self.uses_python_runtime = True
                return self.builder.call(self.runtime["facoh_py_get_global"], [self._string_ptr(node["name"])])
            loaded = self.builder.load(slot, name=f"load_{node['name']}")
            return self.builder.call(self.runtime["facoh_check_defined"], [loaded, self._string_ptr(node["name"])])

        if node_type == "UnaryOperation":
            operator = node["operator"]
            op_id = 1 if operator == "-" else 2 if operator in (
                "not", "!") else None
            if op_id is None:
                raise NotImplementedError(
                    f"Unsupported unary operator: {operator}")
            value = self.compile_expression(node["operand"])
            return self.builder.call(self.runtime["facoh_unary"], [self._const_i32(op_id), value])

        if node_type == "BinaryOperation":
            operator = node["operator"]
            if operator not in _BINARY_OPS:
                raise NotImplementedError(
                    f"Unsupported binary operator: {operator}")
            left = self.compile_expression(node["left"])
            if operator in ("also", "and", "or"):
                function = self.builder.function
                left_block = self.builder.block
                right_block = function.append_basic_block("logic.right")
                merge_block = function.append_basic_block("logic.end")
                truth = self.builder.icmp_signed(
                    "!=", self.builder.call(
                        self.runtime["facoh_truthy"], [left]),
                    self._const_i32(0))
                if operator == "or":
                    self.builder.cbranch(truth, merge_block, right_block)
                else:
                    self.builder.cbranch(truth, right_block, merge_block)
                self.builder.position_at_end(right_block)
                right = self.compile_expression(node["right"])
                right_end = self.builder.block
                right_terminated = right_end.is_terminated
                if not right_terminated:
                    self.builder.branch(merge_block)
                self.builder.position_at_end(merge_block)
                result = self.builder.phi(self.pv, name="logic_value")
                result.add_incoming(left, left_block)
                if not right_terminated:
                    result.add_incoming(right, right_end)
                return result
            right = self.compile_expression(node["right"])
            return self.builder.call(self.runtime["facoh_binary"], [self._const_i32(_BINARY_OPS[operator]), left, right])

        if node_type == "fstring":
            self.uses_python_runtime = True
            raw = node.get("value", "")
            if len(raw) >= 3 and raw[0] in "fF" and raw[1] in "\"'":
                raw = raw[2:-1]
            elif len(raw) >= 2 and raw[0] in "\"'":
                raw = raw[1:-1]
            parts = []
            cursor = 0
            import re
            for match in re.finditer(r"\{([^{}]+)\}", raw):
                if match.start() > cursor:
                    parts.append(self.builder.call(self.runtime["facoh_string"], [
                                 self._string_ptr(raw[cursor:match.start()])]))
                expression_text = match.group(1).strip()
                conversion = None
                if expression_text.endswith(("!r", "!s")):
                    conversion = expression_text[-1]
                    expression_text = expression_text[:-2].strip()
                try:
                    expr_tokens = Lexer(expression_text, "Interpreter").lex()
                    field_parser = Parser(
                        expr_tokens, "Interpreter", expression_text)
                    field_node = field_parser.parse_expression()
                    if conversion:
                        field_node = {"type": "Call", "name": "repr" if conversion == "r" else "str", "arguments": [
                            field_node], "keyword_arguments": {}}
                    parts.append(self.compile_expression(field_node))
                except Exception as error:
                    raise SyntaxError(
                        f"Invalid FACOH f-string field {{{expression_text}}}: {error}") from error
                cursor = match.end()
            if cursor < len(raw):
                parts.append(self.builder.call(self.runtime["facoh_string"], [
                             self._string_ptr(raw[cursor:])]))
            if not parts:
                return self.builder.call(self.runtime["facoh_string"], [self._string_ptr(raw)])
            result = parts[0]
            for part in parts[1:]:
                result = self.builder.call(self.runtime["facoh_binary"], [self._const_i32(
                    1), result, self.builder.call(self.runtime["facoh_py_stringify"], [part])])
            return result

        if node_type == "List":
            value = self.builder.call(self.runtime["facoh_list_new"], [])
            for element in node["elements"]:
                item = self.compile_expression(element)
                self.builder.call(
                    self.runtime["facoh_list_push"], [value, item])
            return value

        if node_type == "Tuple":
            value = self.builder.call(self.runtime["facoh_tuple_new"], [])
            for element in node["elements"]:
                item = self.compile_expression(element)
                self.builder.call(
                    self.runtime["facoh_list_push"], [value, item])
            return value

        if node_type == "Dictionary":
            value = self.builder.call(self.runtime["facoh_dict_new"], [])
            for raw_key, expression in node["contents"].items():
                key_text = str(raw_key)
                try:
                    key_value = ast.literal_eval(key_text)
                except (ValueError, SyntaxError):
                    if key_text == "true":
                        key_value = True
                    elif key_text == "false":
                        key_value = False
                    else:
                        key_value = key_text
                if isinstance(key_value, bool):
                    key = self.builder.call(self.runtime["facoh_bool"], [
                                            self._const_i32(int(key_value))])
                elif isinstance(key_value, int):
                    key = self.builder.call(self.runtime["facoh_int"], [
                                            self._const_i64(key_value)])
                elif isinstance(key_value, float):
                    key = self.builder.call(self.runtime["facoh_float"], [
                                            ir.Constant(self.f64, key_value)])
                else:
                    key = self.builder.call(self.runtime["facoh_string"], [
                                            self._string_ptr(str(key_value))])
                item = self.compile_expression(expression)
                self.builder.call(self.runtime["facoh_dict_set"], [
                                  value, key, item])
            return value

        if node_type == "Index":
            obj = self.builder.load(self._slot_for(node["object"]))
            index = self.compile_expression(node["index"])
            return self.builder.call(self.runtime["facoh_get_item"], [obj, index])

        if node_type == "Slice":
            obj = self.builder.load(self._slot_for(node["object"]))
            start = self._to_i64(self.compile_expression(node["start"]))
            end = self._to_i64(self.compile_expression(node["end"]))
            return self.builder.call(self.runtime["facoh_slice"], [obj, start, end])

        if node_type == "Attribute":
            obj = self.compile_expression(node["object"])
            return self.builder.call(self.runtime["facoh_attr_get"], [obj, self._string_ptr(node["attribute"])])

        if node_type == "MethodCall":
            obj = self.compile_expression(node["object"])
            method_name = node["method"]
            args = [self.compile_expression(arg)
                    for arg in node.get("arguments", [])]
            keyword_args = node.get("keyword_arguments", {})
            if keyword_args:
                first_args, raw_args = self._allocate_temp_array(len(args))
                for index, value in enumerate(args):
                    ptr = self.builder.gep(
                        first_args, [self._const_i64(index)])
                    self.builder.store(value, ptr)

                first_name, raw_names = self._allocate_temp_array(
                    len(keyword_args))
                first_val, raw_vals = self._allocate_temp_array(
                    len(keyword_args))
                for index, (key, expression) in enumerate(keyword_args.items()):
                    name_ptr = self.builder.gep(
                        first_name, [self._const_i64(index)])
                    self.builder.store(self._string_ptr(key), name_ptr)
                    val_ptr = self.builder.gep(
                        first_val, [self._const_i64(index)])
                    self.builder.store(
                        self.compile_expression(expression), val_ptr)

                result = self.builder.call(self.runtime["facoh_method_call_kw"], [obj, self._string_ptr(
                    method_name), first_args, self._const_i64(len(args)), first_name, first_val, self._const_i64(len(keyword_args))])
                self._free_temp_array(raw_args)
                self._free_temp_array(raw_names)
                self._free_temp_array(raw_vals)
                return result

            first_ptr, raw_ptr = self._allocate_temp_array(len(args))
            for index, value in enumerate(args):
                ptr = self.builder.gep(
                    first_ptr, [self._const_i64(index)])
                self.builder.store(value, ptr)
            result = self.builder.call(self.runtime["facoh_method_call"], [
                                       obj, self._string_ptr(method_name), first_ptr, self._const_i64(len(args))])
            self._free_temp_array(raw_ptr)
            return result

        if node_type == "Call":
            if node["name"] in self.object_nodes:
                for expression in node.get("arguments", []):
                    self.compile_expression(expression)
                for expression in node.get("keyword_arguments", {}).values():
                    self.compile_expression(expression)
                obj = self.builder.call(self.runtime["facoh_object_new"], [
                                        self._string_ptr(node["name"])])
                previous_context = self.object_context
                self.object_context = obj
                for object_node in self._object_lineage_nodes(node["name"]):
                    self._compile_block(object_node["initialization"])
                self.object_context = previous_context
                return obj
            if node["name"] in {"Error", "SyntaxError", "IndexError", "ValueError", "NonExistantError", "ZeroDivisionError", "FileNotFoundError", "IndentationError", "TypeError", "KeyError", "TimeoutError", "ConnectionError", "OSError"}:
                args = [self.compile_expression(arg)
                        for arg in node.get("arguments", [])]
                if len(args) > 1:
                    raise ValueError(
                        f"{node['name']}() expects 0 or 1 argument(s)")
                obj = self.builder.call(self.runtime["facoh_object_new"], [
                                        self._string_ptr(node["name"])])
                message = args[0] if args else self.builder.call(
                    self.runtime["facoh_string"], [self._string_ptr("")])
                self.builder.call(self.runtime["facoh_attr_set"], [
                                  obj, self._string_ptr("message"), message])
                return obj
            return self.compile_call(node)

        raise NotImplementedError(f"Unsupported expression: {node_type}")

    def _to_i64(self, value):
        return self.builder.call(self.runtime["facoh_to_i64"], [value])

    def compile_assignment(self, node):
        value = self.compile_expression(node["value"])
        if self.object_context is not None and node["name"] not in self.object_parameter_names:
            self.builder.call(self.runtime["facoh_attr_set"], [
                              self.object_context, self._string_ptr(node["name"]), value])
            return
        slot = self._slot_for(node["name"], create=True)
        self.builder.store(value, slot)

    def compile_call(self, node):
        name = node["name"]
        args = list(node["arguments"])
        keyword_arguments = dict(node.get("keyword_arguments", {}))

        normalized_args = []
        for arg in args:
            if arg.get("type") == "Variable":
                raw_name = arg.get("name", "")
                if "=" in raw_name:
                    keyword, raw_value = raw_name.split("=", 1)
                    keyword = keyword.strip()
                    raw_value = raw_value.strip()
                    if keyword.isidentifier() and raw_value:
                        if keyword in keyword_arguments:
                            raise ValueError(
                                f"{name}() got multiple values for argument '{keyword}'")
                        try:
                            ast.literal_eval(raw_value)
                            expression = {
                                "type": "literal", "value": raw_value}
                        except (ValueError, SyntaxError):
                            if raw_value.isidentifier():
                                expression = {
                                    "type": "Variable", "name": raw_value}
                            else:
                                normalized_args.append(arg)
                                continue
                        keyword_arguments[keyword] = expression
                        continue
            normalized_args.append(arg)

        args = normalized_args
        values = [self.compile_expression(arg) for arg in args]
        if name == "dis":
            if keyword_arguments:
                raise ValueError("dis() does not accept keyword arguments")
            first_ptr, raw_ptr = self._allocate_temp_array(len(values))
            for index, value in enumerate(values):
                ptr = self.builder.gep(
                    first_ptr, [self._const_i64(index)])
                self.builder.store(value, ptr)
            self.builder.call(self.runtime["facoh_print_many"], [
                              first_ptr, self._const_i64(len(values))])
            self._free_temp_array(raw_ptr)
            return self.builder.call(self.runtime["facoh_none"], [])
        if name == "length":
            if len(values) != 1:
                raise ValueError("length() expects exactly one argument")
            length = self.builder.call(
                self.runtime["facoh_list_len"], [values[0]])
            return self.builder.call(self.runtime["facoh_int"], [length])
        if name == "numste":
            if not 1 <= len(values) <= 3:
                raise ValueError("numste() expects one to three arguments")
            zero = ir.Constant(self.i64, 0)
            one = ir.Constant(self.i64, 1)
            if len(values) == 1:
                start, stop, step = zero, self._to_i64(values[0]), one
            elif len(values) == 2:
                start, stop, step = self._to_i64(
                    values[0]), self._to_i64(values[1]), one
            else:
                start, stop, step = self._to_i64(values[0]), self._to_i64(
                    values[1]), self._to_i64(values[2])
            return self.builder.call(self.runtime["facoh_range"], [start, stop, step])
        if name not in self.functions and (name in self.variables or name in self.global_variables):
            self.uses_python_runtime = True
            callable_value = self.builder.load(self._slot_for(name))
            first_args, raw_args = self._allocate_temp_array(len(values))
            for index, value in enumerate(values):
                self.builder.store(value, self.builder.gep(
                    first_args, [self._const_i64(index)]))

            first_names, raw_names = self._allocate_temp_array(
                len(keyword_arguments))
            first_kw_values, raw_kw_values = self._allocate_temp_array(
                len(keyword_arguments))
            for index, (key, expression) in enumerate(keyword_arguments.items()):
                self.builder.store(self._string_ptr(key), self.builder.gep(
                    first_names, [self._const_i64(index)]))
                self.builder.store(self.compile_expression(expression), self.builder.gep(
                    first_kw_values, [self._const_i64(index)]))

            result = self.builder.call(self.runtime["facoh_py_call_value"], [callable_value, first_args, self._const_i64(
                len(values)), first_names, first_kw_values, self._const_i64(len(keyword_arguments))])
            self._free_temp_array(raw_args)
            self._free_temp_array(raw_names)
            self._free_temp_array(raw_kw_values)
            return result
        if name not in self.functions:
            self.uses_python_runtime = True
            first_ptr, raw_ptr = self._allocate_temp_array(len(values))
            for index, value in enumerate(values):
                ptr = self.builder.gep(
                    first_ptr, [self._const_i64(index)])
                self.builder.store(value, ptr)

            first_name_ptr, raw_names = self._allocate_temp_array(
                len(keyword_arguments))
            first_value_ptr, raw_vals = self._allocate_temp_array(
                len(keyword_arguments))
            for index, (key, expression) in enumerate(keyword_arguments.items()):
                name_ptr = self.builder.gep(
                    first_name_ptr, [self._const_i64(index)])
                self.builder.store(self._string_ptr(key), name_ptr)
                val_ptr = self.builder.gep(
                    first_value_ptr, [self._const_i64(index)])
                self.builder.store(
                    self.compile_expression(expression), val_ptr)

            result = self.builder.call(self.runtime["facoh_py_call"], [self._string_ptr(name), first_ptr, self._const_i64(
                len(values)), first_name_ptr, first_value_ptr, self._const_i64(len(keyword_arguments))])
            self._free_temp_array(raw_ptr)
            self._free_temp_array(raw_names)
            self._free_temp_array(raw_vals)
            return result
        fn = self.functions[name]
        parameters = self.function_nodes[name]["parameters"]
        if len(values) > len(parameters):
            raise ValueError(
                f"{name}() expects at most {len(parameters)} argument(s), got {len(values)}")
        ordered = list(values) + [None] * (len(parameters) - len(values))
        provided = set(parameters[:len(values)])
        for keyword, expression in keyword_arguments.items():
            if keyword not in parameters:
                raise ValueError(
                    f"{name}() got an unexpected keyword argument '{keyword}'")
            if keyword in provided:
                raise ValueError(
                    f"{name}() got multiple values for argument '{keyword}'")
            ordered[parameters.index(
                keyword)] = self.compile_expression(expression)
            provided.add(keyword)
        missing = [parameter for parameter, value in zip(
            parameters, ordered) if value is None]
        if missing:
            raise ValueError(
                f"{name}() is missing required argument(s): {', '.join(missing)}")
        values = ordered
        first_ptr, raw_ptr = self._allocate_temp_array(len(values))
        for index, value in enumerate(values):
            ptr = self.builder.gep(
                first_ptr, [self._const_i64(index)])
            self.builder.store(value, ptr)
        result = self.builder.call(
            fn, [first_ptr, self._const_i64(len(values))])
        self._free_temp_array(raw_ptr)
        return result

    def compile_statement(self, node):
        if self.builder.block.is_terminated:
            return
        kind = node["type"]
        if kind == "_context_exit":
            self.builder.call(
                self.runtime["facoh_context_exit"], [node["value"]])
        elif kind == "Assignment":
            self.compile_assignment(node)
        elif kind == "Call":
            self.compile_call(node)
        elif kind == "MethodCall":
            self.compile_expression(node)
        elif kind == "If":
            self._compile_if(node)
        elif kind == "While":
            self._compile_while(node)
        elif kind == "For":
            self._compile_for(node)
        elif kind == "Function" or kind == "Obj":
            return
        elif kind == "AttributeAssignment":
            obj = self.compile_expression(node["object"])
            value = self.compile_expression(node["value"])
            self.builder.call(self.runtime["facoh_attr_set"], [
                              obj, self._string_ptr(node["attribute"]), value])
        elif kind == "throw":
            value = self.compile_expression(node.get("value"))
            self.builder.call(self.runtime["facoh_throw_value"], [value])
            self.builder.unreachable()
        elif kind == "try":
            self._compile_try(node)
        elif kind == "return":
            if self.builder.function.name == "main":
                raise SyntaxError(
                    "return is only supported inside FACOH functions")
            return_value = self.compile_expression(node.get("value"))
            for previous_handler in reversed(self.handler_stack):
                self.builder.call(self.runtime["facoh_handler_set"], [
                                  previous_handler])
            for finally_block in reversed(list(self.finally_stack)):
                removed_index = None
                for index in range(len(self.finally_stack) - 1, -1, -1):
                    if self.finally_stack[index] is finally_block:
                        removed_index = index
                        self.finally_stack.pop(index)
                        break
                self._compile_block(finally_block)
                if removed_index is not None:
                    self.finally_stack.insert(removed_index, finally_block)
                if self.builder.block.is_terminated:
                    return
            self.builder.ret(return_value)
        elif kind == "break":
            if not self.loop_stack:
                raise SyntaxError("break used outside a loop")
            for previous_handler in reversed(self.handler_stack):
                self.builder.call(self.runtime["facoh_handler_set"], [
                                  previous_handler])
            for finalizer in reversed(list(self.finally_stack)):
                self._compile_finalizer_body(finalizer)
                if self.builder.block.is_terminated:
                    return
            loop = self.loop_stack[-1]
            if loop["broke"] is not None:
                self.builder.store(ir.Constant(
                    ir.IntType(1), 1), loop["broke"])
            self.builder.branch(loop["exit"])
        elif kind == "pass":
            return
        elif kind == "use":
            self.uses_python_runtime = True
            module_name = node.get("name", "unknown")
            if node.get("from") is not None:
                raise NotImplementedError(
                    f"Unsupported native import form for '{module_name}'")
            if module_name in {"threading", "multiprocessing"}:
                module_value = self.builder.call(self.runtime["facoh_py_import_module"], [
                                                 self._string_ptr(module_name)])
            elif module_name in {"ui", "lan", "web_api", "web_ui", "db", "graphics", "fcharrays"}:
                # Search candidate locations for the extension
                candidate_paths = [
                    self.filename.parent / "extensions" / module_name / "main.py",
                    self.filename.parent / "extensions" /
                    module_name / f"{module_name}.py",
                    self.filename.parent / "extensions" / f"{module_name}.py",
                    self.filename.parent / f"{module_name}.py",
                    Path(__file__).resolve().parent /
                    "extensions" / module_name / "main.py",
                    Path(__file__).resolve().parent / "extensions" /
                    module_name / f"{module_name}.py",
                    Path(__file__).resolve().parent /
                    "extensions" / f"{module_name}.py",
                    Path(__file__).resolve().parent / f"{module_name}.py",
                ]
                extension_path = candidate_paths[0]
                for cp in candidate_paths:
                    if cp.exists():
                        extension_path = cp.resolve()
                        break
                module_value = self.builder.call(self.runtime["facoh_py_load_extension"], [
                                                 self._string_ptr(module_name), self._string_ptr(str(extension_path))])
            else:
                raise NotImplementedError(
                    f"Unsupported native module: {module_name}")
            variable_name = node.get("var") or module_name
            self.builder.store(module_value, self._slot_for(
                variable_name, create=True))
        elif kind == "fileoc":
            self.uses_python_runtime = True
            context = self.compile_expression(node.get("expression"))
            entered = self.builder.call(
                self.runtime["facoh_context_enter"], [context])
            if node.get("var"):
                self.builder.store(entered, self._slot_for(
                    node["var"], create=True))
            previous_handler = self.builder.call(
                self.runtime["facoh_handler_get"], [])
            buffer = self._new_entry_alloca(
                "fileoc_exception_buffer", ir.ArrayType(self.i8, 256))
            buffer_ptr = self.builder.gep(
                buffer, [self._const_i32(0), self._const_i32(0)])
            self.builder.call(self.runtime["facoh_handler_set"], [buffer_ptr])
            self.handler_stack.append(previous_handler)
            finalizer = [{"type": "_context_exit", "value": context}]
            self.finally_stack.append(finalizer)
            if os.name == "nt":
                frame = self.builder.call(
                    self.frameaddress, [self._const_i32(0)])
                setjmp_result = self.builder.call(
                    self.runtime[self.setjmp_name], [buffer_ptr, frame])
            else:
                setjmp_result = self.builder.call(
                    self.runtime[self.setjmp_name], [buffer_ptr])
            is_initial = self.builder.icmp_signed(
                "==", setjmp_result, self._const_i32(0))
            body_block = self.builder.function.append_basic_block(
                "fileoc.body")
            error_block = self.builder.function.append_basic_block(
                "fileoc.error")
            merge_block = self.builder.function.append_basic_block(
                "fileoc.end")
            self.builder.cbranch(is_initial, body_block, error_block)
            self.builder.position_at_end(body_block)
            self._compile_block(node.get("block", []))
            self.finally_stack.pop()
            self.handler_stack.pop()
            if not self.builder.block.is_terminated:
                self.builder.call(self.runtime["facoh_handler_set"], [
                                  previous_handler])
                self._compile_block(finalizer)
                if not self.builder.block.is_terminated:
                    self.builder.branch(merge_block)
            self.builder.position_at_end(error_block)
            self.builder.call(self.runtime["facoh_handler_set"], [
                              previous_handler])
            self.builder.call(self.runtime["facoh_py_yield"], [])
            suppressed = self.builder.call(
                self.runtime["facoh_context_exit_error"], [context])
            rethrow_block = self.builder.function.append_basic_block(
                "fileoc.rethrow")
            suppress_condition = self.builder.icmp_signed(
                "!=", suppressed, self._const_i32(0))
            self.builder.cbranch(suppress_condition,
                                 merge_block, rethrow_block)
            self.builder.position_at_end(rethrow_block)
            self.builder.call(self.runtime["facoh_rethrow"], [])
            self.builder.unreachable()
            self.builder.position_at_end(merge_block)
        elif kind == "delete":
            target = node.get("target")
            if isinstance(target, dict) and target.get("type") == "Variable":
                name = target["name"]
                if name not in self.variables and name not in self.global_variables:
                    raise NameError(f"Variable '{name}' does not exist")
                self.builder.store(self.builder.call(
                    self.runtime["facoh_unbound"], []), self._slot_for(name))
            elif isinstance(target, dict) and target.get("type") == "Attribute":
                obj = self.compile_expression(target["object"])
                self.builder.call(self.runtime["facoh_attr_del"], [
                                  obj, self._string_ptr(target["attribute"])])
            else:
                raise NotImplementedError(
                    "Unsupported delete target in native compiler")
        elif kind in {
            "Variable", "BinaryOperation", "UnaryOperation",
            "literal", "fstring", "List", "Tuple", "Dictionary",
            "Index", "Slice", "Attribute"
        }:
            self.compile_expression(node)
        else:
            raise NotImplementedError(f"Unsupported statement: {kind}")

    def _compile_block(self, nodes):
        for node in nodes:
            if self.builder.block.is_terminated:
                break
            self.compile_statement(node)
            if self.needs_thread_yield and not self.builder.block.is_terminated and node.get("type") in {"If", "try", "fileoc"}:
                self.builder.call(self.runtime["facoh_py_yield"], [])

    def _compile_try(self, node):
        function = self.builder.function
        previous_handler = self.builder.call(
            self.runtime["facoh_handler_get"], [])
        buffer_type = ir.ArrayType(self.i8, 256)
        buffer = self._new_entry_alloca("exception_buffer", buffer_type)
        buffer_ptr = self.builder.gep(
            buffer, [self._const_i32(0), self._const_i32(0)])
        self.builder.call(self.runtime["facoh_handler_set"], [buffer_ptr])
        self.handler_stack.append(previous_handler)
        finalizer = node.get("finally_block")
        if finalizer:
            self.finally_stack.append(finalizer)
        if os.name == "nt":
            frame = self.builder.call(self.frameaddress, [self._const_i32(0)])
            setjmp_result = self.builder.call(
                self.runtime[self.setjmp_name], [buffer_ptr, frame])
        else:
            setjmp_result = self.builder.call(
                self.runtime[self.setjmp_name], [buffer_ptr])
        is_initial = self.builder.icmp_signed(
            "==", setjmp_result, self._const_i32(0))
        try_block = function.append_basic_block("try.body")
        dispatch_block = function.append_basic_block("try.dispatch")
        merge_block = function.append_basic_block("try.end")
        self.builder.cbranch(is_initial, try_block, dispatch_block)

        self.builder.position_at_end(try_block)
        self._compile_block(node.get("block", []))
        if not self.builder.block.is_terminated:
            self.builder.call(self.runtime["facoh_handler_set"], [
                              previous_handler])
            if node.get("else_block"):
                self._compile_block(node["else_block"])
            if not self.builder.block.is_terminated:
                if finalizer:
                    self._compile_finalizer_body(finalizer)
                if not self.builder.block.is_terminated:
                    self.builder.branch(merge_block)

        self.builder.position_at_end(dispatch_block)
        self.builder.call(self.runtime["facoh_handler_set"], [
                          previous_handler])
        self.handler_stack.pop()
        caughts = list((node.get("caughts") or {}).values())
        next_test = self.builder.block
        for index, caught in enumerate(caughts):
            self.builder.position_at_end(next_test)
            caught_type = caught.get("type")
            if caught_type:
                matches = self.builder.call(self.runtime["facoh_error_matches"], [
                                            self._string_ptr(caught_type)])
                condition = self.builder.icmp_signed(
                    "!=", matches, self._const_i32(0))
            else:
                condition = ir.Constant(ir.IntType(1), 1)
            catch_block = function.append_basic_block(f"try.catch.{index}")
            next_block = function.append_basic_block(f"try.next.{index}")
            self.builder.cbranch(condition, catch_block, next_block)
            self.builder.position_at_end(catch_block)
            if caught.get("var"):
                self.builder.store(self.builder.call(self.runtime["facoh_error_value"], [
                ]), self._slot_for(caught["var"], create=True))
            self._compile_block(caught.get("block", []))
            if not self.builder.block.is_terminated:
                if finalizer:
                    self._compile_finalizer_body(finalizer)
                if not self.builder.block.is_terminated:
                    self.builder.branch(merge_block)
            next_test = next_block
        self.builder.position_at_end(next_test)
        if finalizer:
            self._compile_finalizer_body(finalizer)
        if not self.builder.block.is_terminated:
            self.builder.call(self.runtime["facoh_rethrow"], [])
            self.builder.unreachable()

        if finalizer:
            for index in range(len(self.finally_stack)-1, -1, -1):
                if self.finally_stack[index] is finalizer:
                    self.finally_stack.pop(index)
                    break
        self.builder.position_at_end(merge_block)

    def _compile_if(self, node):
        condition_value = self.compile_expression(node["condition"])
        condition = self.builder.icmp_signed(
            "!=", self.builder.call(
                self.runtime["facoh_truthy"], [condition_value]),
            self._const_i32(0))
        function = self.builder.function
        then_block = function.append_basic_block("if.then")
        else_block = function.append_basic_block("if.else")
        merge_block = function.append_basic_block("if.end")
        self.builder.cbranch(condition, then_block, else_block)

        self.builder.position_at_end(then_block)
        self._compile_block(node.get("block", []))
        if not self.builder.block.is_terminated:
            self.builder.branch(merge_block)

        self.builder.position_at_end(else_block)
        self._compile_block(node.get("else_block") or [])
        if not self.builder.block.is_terminated:
            self.builder.branch(merge_block)

        self.builder.position_at_end(merge_block)

    def _compile_loop_else(self, node, broke, prefix):
        else_nodes = node.get("else_block") or []
        if not else_nodes:
            return
        should_else = self.builder.load(broke)
        should_else = self.builder.not_(should_else)
        function = self.builder.function
        else_block = function.append_basic_block(f"{prefix}.else")
        end_block = function.append_basic_block(f"{prefix}.end")
        self.builder.cbranch(should_else, else_block, end_block)
        self.builder.position_at_end(else_block)
        self._compile_block(else_nodes)
        if not self.builder.block.is_terminated:
            self.builder.branch(end_block)
        self.builder.position_at_end(end_block)

    def _compile_while(self, node):
        function = self.builder.function
        cond_block = function.append_basic_block("while.cond")
        body_block = function.append_basic_block("while.body")
        exit_block = function.append_basic_block("while.exit")
        broke = self._new_entry_alloca("while_broke", ir.IntType(1))
        self.builder.store(ir.Constant(ir.IntType(1), 0), broke)
        self.builder.branch(cond_block)

        self.builder.position_at_end(cond_block)
        if self.needs_thread_yield:
            self.builder.call(self.runtime["facoh_py_yield"], [])
        condition_value = self.compile_expression(node["condition"])
        condition = self.builder.icmp_signed(
            "!=", self.builder.call(
                self.runtime["facoh_truthy"], [condition_value]),
            self._const_i32(0))
        self.builder.cbranch(condition, body_block, exit_block)

        self.builder.position_at_end(body_block)
        self.loop_stack.append({"exit": exit_block, "broke": broke})
        self._compile_block(node.get("block", []))
        self.loop_stack.pop()
        if not self.builder.block.is_terminated:
            if self.needs_thread_yield:
                self.builder.call(self.runtime["facoh_py_yield"], [])
            self.builder.branch(cond_block)

        self.builder.position_at_end(exit_block)
        self._compile_loop_else(node, broke, "while")

    def _compile_for(self, node):
        iterable = self.compile_expression(node.get("iterable"))
        iterator = self.builder.call(
            self.runtime["facoh_iter_new"], [iterable])
        broke = self._new_entry_alloca("for_broke", ir.IntType(1))
        self.builder.store(ir.Constant(ir.IntType(1), 0), broke)
        variable_slot = self._slot_for(node["variable"], create=True)
        function = self.builder.function
        cond_block = function.append_basic_block("for.cond")
        body_block = function.append_basic_block("for.body")
        exit_block = function.append_basic_block("for.exit")
        self.builder.branch(cond_block)
        self.builder.position_at_end(cond_block)
        has_next = self.builder.call(
            self.runtime["facoh_iter_has_next"], [iterator])
        condition = self.builder.icmp_signed(
            "!=", has_next, self._const_i32(0))
        self.builder.cbranch(condition, body_block, exit_block)
        self.builder.position_at_end(body_block)
        item = self.builder.call(self.runtime["facoh_iter_next"], [iterator])
        self.builder.store(item, variable_slot)
        self.loop_stack.append({"exit": exit_block, "broke": broke})
        self._compile_block(node.get("block", []))
        self.loop_stack.pop()
        if not self.builder.block.is_terminated:
            if self.needs_thread_yield:
                self.builder.call(self.runtime["facoh_py_yield"], [])
            self.builder.branch(cond_block)
        self.builder.position_at_end(exit_block)
        self._compile_loop_else(node, broke, "for")

    def _compile_finalizer_body(self, finalizer):
        removed_index = None
        for index in range(len(self.finally_stack) - 1, -1, -1):
            if self.finally_stack[index] is finalizer:
                removed_index = index
                self.finally_stack.pop(index)
                break
        self._compile_block(finalizer)
        if removed_index is not None:
            self.finally_stack.insert(removed_index, finalizer)


class _ManifestParser:
    """Parser for FACOH's manifest.fch key = value format."""

    def __init__(self, source, filename="manifest.fch"):
        import re
        self.filename = str(filename)
        token_pattern = re.compile(
            r'''\s*(?:("(?:\\.|[^"\\])*")|('(?:\\.|[^'\\])*')|([{}\[\],=])|([^\s{}\[\],=]+))'''
        )
        self.tokens = []
        position = 0
        while position < len(source):
            match = token_pattern.match(source, position)
            if not match:
                if source[position:].strip() == "":
                    break
                raise ValueError(
                    f"{self.filename}: invalid syntax at character {position + 1}")
            position = match.end()
            quoted_double, quoted_single, punctuation, bare = match.groups()
            token = quoted_double or quoted_single or punctuation or bare
            if token is not None:
                self.tokens.append(token)
        self.index = 0

    def _peek(self):
        return self.tokens[self.index] if self.index < len(self.tokens) else None

    def _take(self, expected=None):
        token = self._peek()
        if token is None:
            raise ValueError(f"{self.filename}: unexpected end of file")
        if expected is not None and token != expected:
            raise ValueError(
                f"{self.filename}: expected {expected!r}, got {token!r}")
        self.index += 1
        return token

    def _string(self, token):
        import ast
        try:
            value = ast.literal_eval(token)
        except (SyntaxError, ValueError) as error:
            raise ValueError(
                f"{self.filename}: invalid string literal {token!r}") from error
        if not isinstance(value, str):
            raise ValueError(f"{self.filename}: expected a quoted string")  # noqa: TRY004
        return value

    def _value(self):
        token = self._peek()
        if token == "{":
            return self._object()
        if token == "[":
            return self._array()
        if token is None:
            raise ValueError(f"{self.filename}: expected a value")
        token = self._take()
        if token.startswith(('"', "'")):
            return self._string(token)
        if token in {"true", "false"}:
            return token == "true"
        if token == "null":
            return None
        try:
            return int(token) if token.isdigit() or (
                token.startswith("-") and token[1:].isdigit()) else float(token)
        except ValueError:
            raise ValueError(
                f"{self.filename}: values must be quoted strings, objects, arrays, numbers, booleans, or null; got {token!r}")

    def _object(self):
        self._take("{")
        result = {}
        while self._peek() != "}":
            token = self._peek()
            if token is None:
                raise ValueError(f"{self.filename}: unclosed object")
            if not token.startswith(('"', "'")):
                raise ValueError(
                    f"{self.filename}: object keys must be quoted strings, got {token!r}")
            key = self._string(self._take())
            if key in result:
                raise ValueError(f"{self.filename}: duplicate field {key!r}")
            self._take("=")
            result[key] = self._value()
            if self._peek() == ",":
                self._take(",")
                if self._peek() == "}":
                    break
            elif self._peek() != "}":
                raise ValueError(
                    f"{self.filename}: expected ',' or '}}' after field {key!r}")
        self._take("}")
        return result

    def _array(self):
        self._take("[")
        result = []
        while self._peek() != "]":
            if self._peek() is None:
                raise ValueError(f"{self.filename}: unclosed array")
            result.append(self._value())
            if self._peek() == ",":
                self._take(",")
                if self._peek() == "]":
                    break
            elif self._peek() != "]":
                raise ValueError(
                    f"{self.filename}: expected ',' or ']' in array")
        self._take("]")
        return result

    def parse(self):
        value = self._object()
        if self._peek() is not None:
            raise ValueError(
                f"{self.filename}: unexpected token {self._peek()!r} after root object")
        return value


def _required_manifest_field(mapping, key, prefix, expected_type=None):
    field_path = f"{prefix}.{key}" if prefix else key
    if key not in mapping:
        raise ValueError(
            f"manifest.fch: missing required field '{field_path}'")
    value = mapping[key]
    if expected_type is not None and not isinstance(value, expected_type):
        expected_name = {
            str: "a string", list: "an array of strings", dict: "an object"
        }.get(expected_type, expected_type.__name__)
        raise ValueError(
            f"manifest.fch: field '{field_path}' must be {expected_name}")
    if expected_type is list and any(not isinstance(item, str) for item in value):
        raise ValueError(
            f"manifest.fch: every item in '{field_path}' must be a string")
    if isinstance(value, str) and not value.strip():
        raise ValueError(f"manifest.fch: field '{field_path}' cannot be empty")
    return value


def _read_manifest(project_path):
    """Read a project's manifest.fch using FACOH's manifest syntax."""
    project_path = Path(project_path).resolve()
    manifest_path = project_path / "manifest.fch"
    if not manifest_path.is_file():
        raise FileNotFoundError(f"Project manifest not found: {manifest_path}")
    try:
        manifest = _ManifestParser(
            manifest_path.read_text(encoding="utf-8"), manifest_path
        ).parse()
    except (OSError, UnicodeError) as error:
        raise ValueError(f"Could not read {manifest_path}: {error}") from error
    if not isinstance(manifest, dict):
        raise TypeError("manifest.fch: root value must be an object")
    return project_path, manifest


def _safe_main_path(project_path, main_value, section_name):
    main_path = (project_path / main_value).resolve()
    try:
        main_path.relative_to(project_path)
    except ValueError as error:
        raise ValueError(
            f"manifest.fch: {section_name}.main must point to a file inside the project folder"
        ) from error
    if main_path.suffix != ".fch":
        raise ValueError(
            f"manifest.fch: {section_name}.main must reference a .fch file: {main_value}"
        )
    if not main_path.is_file():
        raise FileNotFoundError(
            f"manifest.fch: main file does not exist: {main_value}"
        )
    return main_path


def _load_project_manifest(project_path):
    """Validate a normal project manifest and return its entry point."""
    project_path, manifest = _read_manifest(project_path)
    project = _required_manifest_field(manifest, "project", "", dict)
    _required_manifest_field(project, "name", "project", str)
    _required_manifest_field(project, "version", "project", str)
    _required_manifest_field(project, "author", "project", dict)
    _required_manifest_field(project["author"], "name", "project.author", str)
    _required_manifest_field(project, "engine", "project", str)
    _required_manifest_field(project, "engineVersion", "project", str)
    project_type = _required_manifest_field(project, "type", "project", str)
    if project_type == "mod":
        raise ValueError(
            "This project has type 'mod'; use 'cmod' to package it as a .fmod file"
        )
    main_value = _required_manifest_field(project, "main", "project", str)
    if "description" in project:
        _required_manifest_field(project, "description", "project", str)
    if "build" in manifest:
        build = manifest["build"]
        if not isinstance(build, dict):
            raise ValueError("manifest.fch: field 'build' must be an object")
        _required_manifest_field(build, "date", "build", str)
        _required_manifest_field(build, "targetPlatforms", "build", list)
    main_path = _safe_main_path(project_path, main_value, "project")
    return project_path, manifest, main_path


def _load_mod_manifest(project_path):
    """Validate the user's mod manifest format before creating a .fmod package."""
    project_path, manifest = _read_manifest(project_path)
    if "mod" in manifest:
        mod = _required_manifest_field(manifest, "mod", "", dict)
        section_name = "mod"
    elif "project" in manifest and isinstance(manifest["project"], dict):
        project_type = manifest["project"].get("type")
        if project_type != "mod":
            raise ValueError(
                f"cmod only works with projects whose type is 'mod'; got {project_type!r}"
            )
        # Also accept the shared 'project' root for users who prefer one
        # manifest section name for every project type.
        mod = manifest["project"]
        section_name = "project"
    else:
        raise ValueError(
            "cmod requires a 'mod' manifest section (or a 'project' section with type = 'mod')"
        )
    _required_manifest_field(mod, "name", section_name, str)
    _required_manifest_field(mod, "version", section_name, str)
    _required_manifest_field(mod, "description", section_name, str)
    _required_manifest_field(mod, "author", section_name, dict)
    _required_manifest_field(mod["author"], "name", f"{section_name}.author", str)
    _required_manifest_field(mod, "host", section_name, str)
    _required_manifest_field(mod, "hosttype", section_name, str)
    mod_type = _required_manifest_field(mod, "type", section_name, str)
    if mod_type != "mod":
        raise ValueError(
            f"cmod requires manifest.fch field 'mod.type' to equal 'mod', got {mod_type!r}"
        )
    main_value = _required_manifest_field(mod, "main", section_name, str)
    addons = _required_manifest_field(manifest, "addons", "", list)
    if not addons:
        raise ValueError("manifest.fch: field 'addons' must contain at least one addon category")
    if any(not isinstance(addon, str) or not addon.strip() for addon in addons):
        raise ValueError("manifest.fch: every item in 'addons' must be a non-empty string")

    # Dependencies are optional, but when present must map dependency names to versions.
    dependencies = manifest.get("dependencies", {})
    if not isinstance(dependencies, dict):
        raise ValueError("manifest.fch: field 'dependencies' must be an object")  # noqa: TRY004
    for dependency_name, version in dependencies.items():
        if not dependency_name.strip():
            raise ValueError("manifest.fch: dependency names cannot be empty")
        if not isinstance(version, str) or not version.strip():
            raise ValueError(
                f"manifest.fch: dependency '{dependency_name}' must have a non-empty version string"
            )

    main_path = _safe_main_path(project_path, main_value, section_name)
    # Mod dependencies used for mod-on-mod extensions are vendored here.
    # Check both identity and version before packaging to avoid broken mods.
    hostmods_path = project_path / "src" / "hostmods"
    if hostmods_path.exists() and not hostmods_path.is_dir():
        raise ValueError("Mod path 'src/hostmods' must be a directory")
    if dependencies and not hostmods_path.is_dir():
        first_dependency = next(iter(dependencies))
        raise FileNotFoundError(
            f"Dependency '{first_dependency}' is declared, but src/hostmods/{first_dependency}.fmod is missing"
        )
    if hostmods_path.is_dir():
        import zipfile
        for dependency_name, required_version in dependencies.items():
            dependency_path = hostmods_path / f"{dependency_name}.fmod"
            if not dependency_path.is_file():
                raise FileNotFoundError(
                    f"Dependency '{dependency_name}' is declared, but '{dependency_path.relative_to(project_path).as_posix()}' does not exist"
                )
            try:
                with zipfile.ZipFile(dependency_path, "r") as dependency_archive:
                    dependency_manifest_text = dependency_archive.read("manifest.fch").decode("utf-8")
                dependency_manifest = _ManifestParser(
                    dependency_manifest_text, dependency_path
                ).parse()
            except (OSError, UnicodeError, KeyError, zipfile.BadZipFile) as error:
                raise ValueError(
                    f"Dependency '{dependency_name}' is not a valid .fmod package with manifest.fch"
                ) from error
            dependency_mod = dependency_manifest.get("mod", dependency_manifest.get("project", {}))
            if not isinstance(dependency_mod, dict):
                raise ValueError(  # noqa: TRY004
                    f"Dependency '{dependency_name}' has an invalid manifest"
                )
            actual_version = dependency_mod.get("version")
            if actual_version != required_version:
                raise ValueError(
                    f"Dependency '{dependency_name}' requires version {required_version}, found {actual_version!r}"
                )

    return project_path, manifest, main_path


def compile_folder(project_path, output_path=None):
    """Compile a normal FACOH project folder to a native executable."""
    project_path, manifest, main_path = _load_project_manifest(project_path)
    project = manifest["project"]
    if output_path is None:
        project_name = project["name"].strip()
        project_version = project["version"].strip()
        output_name = project_name + " v" + project_version + (".exe" if os.name == "nt" else ".out")
        output_path = project_path / output_name
    else:
        output_path = Path(output_path).resolve()
        if output_path.suffix.lower() not in {".exe", ".out"}:
            raise ValueError("Native project output must use .exe on Windows or .out on other platforms")

    source = main_path.read_text(encoding="utf-8")
    Compiler(source, main_path).compile(output_path)
    return output_path


def compile_mod_folder(project_path, output_path=None):
    """Create a .fmod archive containing a validated FACOH mod project.

    .fmod is currently a packaged mod (manifest, FACOH source, and assets),
    not a dynamically loadable native library. The host mod loader executes
    the packaged entry point through its FACOH runtime/adapter.
    """
    import zipfile

    project_path, manifest, _ = _load_mod_manifest(project_path)
    mod = manifest["project"]
    if output_path is None:
        safe_name = "".join(
            char if char.isalnum() or char in "-_" else "_"
            for char in mod["name"].strip()
        ).strip("_") or "mod"
        output_path = project_path / f"{safe_name}-v{mod['version']}.fmod"
    else:
        output_path = Path(output_path).resolve()
        if output_path.suffix.lower() != ".fmod":
            raise ValueError("cmod output must use the .fmod extension")

    # Never include VCS metadata, Python caches, or the output archive itself.
    excluded_dirs = {".git", "__pycache__", ".pytest_cache", ".mypy_cache"}
    output_resolved = output_path.resolve()
    with zipfile.ZipFile(output_resolved, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(project_path.rglob("*")):
            if not path.is_file() or path.resolve() == output_resolved:
                continue
            relative = path.relative_to(project_path)
            if any(part in excluded_dirs for part in relative.parts):
                continue
            if path.suffix in {".pyc", ".pyo"}:
                continue
            archive.write(path, relative.as_posix())
    return output_resolved


def cmod(project_path, output_path=None):
    """Public command entry point for building a .fmod mod package."""
    return compile_mod_folder(project_path, output_path)


if __name__ == "__main__":
    import argparse

    cli = argparse.ArgumentParser(
        description="Compile FACOH projects to native executables or .fmod mod packages"
    )
    cli.add_argument(
        "source",
        help="Project directory, manifest.fch, or command 'compile'/'cmod'",
    )
    cli.add_argument(
        "project", nargs="?",
        help="Project directory or manifest.fch when using 'compile' or 'cmod'",
    )
    cli.add_argument("-o", "--output", help="Output executable or .fmod archive path")
    args = cli.parse_args()

    command = args.source if args.source in {"compile", "cmod"} else "compile"
    selected_source = args.project if command in {"compile", "cmod"} and args.project else args.source
    if command in {"compile", "cmod"} and args.source in {"compile", "cmod"} and not args.project:
        cli.error(f"{args.source} requires a project directory or manifest.fch")

    source_path = Path(selected_source)
    project_path = source_path.parent if source_path.name == "manifest.fch" else source_path
    try:
        if command == "cmod":
            output_path = compile_mod_folder(project_path, args.output)
        elif source_path.is_dir() or source_path.name == "manifest.fch":
            output_path = compile_folder(project_path, args.output)
        else:
            output_path = Path(args.output) if args.output else source_path.with_suffix(
                ".exe" if os.name == "nt" else ".out")
            Compiler(source_path.read_text(encoding="utf-8"), source_path).compile(output_path)
        print(f"Compiled successfully: {output_path}")
    except (NotImplementedError, SyntaxError, TypeError, ValueError, NameError,
            FileNotFoundError, OSError, RuntimeError, subprocess.CalledProcessError) as error:
        print(f"FACOH compiler error: {error}", file=sys.stderr)
        raise SystemExit(1)
