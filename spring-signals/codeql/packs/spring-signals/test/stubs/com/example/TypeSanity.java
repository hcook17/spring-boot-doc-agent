package com.example;

/** Stub type hierarchy for TypesSanity.ql. */
interface InterfaceA { }

interface InterfaceB extends InterfaceA { }

class BaseClass implements InterfaceA { }

class DerivedClass extends BaseClass implements InterfaceB { }
