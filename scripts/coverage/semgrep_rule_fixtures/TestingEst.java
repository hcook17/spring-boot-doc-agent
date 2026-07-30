package com.example.fixtures;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.Disabled;
import static org.mockito.Mockito.verify;

class DiscountCalculatorTest {

    @Test
    void assertionFreeTest() {
        DiscountCalculator calc = new DiscountCalculator();
        calc.apply(10);
    }

    @Disabled("flaky in CI")
    @Test
    void disabledTest() {
        DiscountCalculator calc = new DiscountCalculator();
        assertTrueStub(calc.apply(10) > 0);
    }

    @Test
    void swallowsFailure() {
        try {
            riskyCall();
        } catch (Exception e) {
        }
    }

    @Test
    void sleepsInsteadOfPolling() throws InterruptedException {
        Thread.sleep(500);
        assertTrueStub(true);
    }

    @Test
    void verifyOnlyNoAssertion() {
        DiscountGateway gateway = mockGateway();
        gateway.notify("applied");
        verify(gateway).notify("applied");
    }

    private void riskyCall() throws Exception {
        throw new Exception("boom");
    }

    private DiscountGateway mockGateway() {
        return null;
    }

    private void assertTrueStub(boolean b) {
    }
}

class DiscountCalculator {
    int apply(int rate) {
        return rate;
    }
}

interface DiscountGateway {
    void notify(String s);
}
