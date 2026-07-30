package com.example.fixtures;

import io.micrometer.core.instrument.MeterRegistry;

public class Metrics {
    private MeterRegistry registry;

    @Timed
    public void tracked() { }
}
