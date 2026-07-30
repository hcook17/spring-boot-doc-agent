package com.example.fixtures.negative;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.mock;

/** Negative corpus: shapes that must NOT fire testing_est rules. */
class DiscountCalculatorNegativeTest {

    @Test
    void assertsOutcome() {
        DiscountCalculator calc = new DiscountCalculator();
        assertEquals(10, calc.apply(10));
    }

    @Test
    void enabledAndAsserting() {
        assertTrue(true);
    }

    @Test
    void catchRethrows() {
        assertThrows(Exception.class, this::riskyCall);
    }

    @Test
    void noSleepJustAssert() {
        assertEquals(1, 1);
    }

    @Test
    void verifyAndAssert() {
        DiscountGateway gateway = mock(DiscountGateway.class);
        gateway.notify("applied");
        verify(gateway).notify("applied");
        assertEquals("applied", "applied");
    }

    private void riskyCall() throws Exception {
        throw new Exception("boom");
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
