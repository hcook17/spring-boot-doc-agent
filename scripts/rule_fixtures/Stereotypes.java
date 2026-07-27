package com.example.fixtures;

@Service
public class BillingService {
    void charge() { }
}

@Service("namedService")
class NamedService { }

@Component
class Helper { }

@Configuration
class WiringConfig { }
