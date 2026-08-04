package com.example;

import io.micrometer.core.annotation.Timed;
import io.micrometer.core.instrument.MeterRegistry;

public class ObservabilityService {
    private final MeterRegistry meterRegistry;

    public ObservabilityService(MeterRegistry meterRegistry) {
        this.meterRegistry = meterRegistry;
    }

    @Timed
    public String timed() {
        return "ok";
    }
}
