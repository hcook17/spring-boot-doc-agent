package com.example.billing;

import io.micrometer.core.annotation.Timed;

class TimedComponent {
    @Timed
    public void tracked() { }
}
