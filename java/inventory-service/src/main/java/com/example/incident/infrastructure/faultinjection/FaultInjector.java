package com.example.incident.infrastructure.faultinjection;

import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Component;

import java.util.Map;

@Slf4j
@Component
@RequiredArgsConstructor
public class FaultInjector {

    private final FaultConfig faultConfig;

    public boolean isActive(String faultId) {
        if (!faultConfig.isEnabled()) {
            return false;
        }
        FaultConfig.FaultToggle toggle = faultConfig.getToggles().get(faultId);
        return toggle != null && toggle.isActive();
    }

    public Map<String, Object> getParameters(String faultId) {
        FaultConfig.FaultToggle toggle = faultConfig.getToggles().get(faultId);
        return toggle != null ? toggle.getParameters() : Map.of();
    }

    public void simulateSlowResponse(String faultId, Runnable operation) {
        if (!isActive(faultId)) {
            operation.run();
            return;
        }

        Map<String, Object> params = getParameters(faultId);
        long delayMs = params.containsKey("delay_ms")
                ? ((Number) params.get("delay_ms")).longValue()
                : 1000;

        log.warn("Fault injection: {} - simulating {}ms delay", faultId, delayMs);
        try {
            Thread.sleep(delayMs);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }
        operation.run();
    }

    public <T> T simulateSlowResponse(String faultId, java.util.function.Supplier<T> operation) {
        if (!isActive(faultId)) {
            return operation.get();
        }

        Map<String, Object> params = getParameters(faultId);
        long delayMs = params.containsKey("delay_ms")
                ? ((Number) params.get("delay_ms")).longValue()
                : 1000;

        log.warn("Fault injection: {} - simulating {}ms delay", faultId, delayMs);
        try {
            Thread.sleep(delayMs);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }
        return operation.get();
    }

    public void simulateException(String faultId, String exceptionType) {
        if (!isActive(faultId)) {
            return;
        }

        log.warn("Fault injection: {} - throwing {}", faultId, exceptionType);
        switch (exceptionType) {
            case "TIMEOUT":
                throw new RuntimeException("Simulated timeout: " + faultId);
            case "CONNECTION_REFUSED":
                throw new RuntimeException("Simulated connection refused: " + faultId);
            case "NULL_POINTER":
                throw new NullPointerException("Simulated NPE: " + faultId);
            case "SERVICE_UNAVAILABLE":
                throw new RuntimeException("Simulated 503 Service Unavailable: " + faultId);
            default:
                throw new RuntimeException("Simulated fault: " + faultId);
        }
    }
}
