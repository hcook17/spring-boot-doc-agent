package com.example.fixture;

import org.springframework.boot.autoconfigure.SpringBootApplication;

/**
 * Present so Probe.ql's springbootapplication_reaches_configuration check has a
 * reference to resolve. CodeQL only extracts library types the source actually
 * references, so an unreferenced annotation type is absent from the database and
 * the probe reports 0 for reasons unrelated to extractor behaviour.
 */
@SpringBootApplication
public class Application {}
