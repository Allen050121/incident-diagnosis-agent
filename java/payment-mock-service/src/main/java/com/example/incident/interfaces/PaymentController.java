package com.example.incident.interfaces;

import com.example.incident.infrastructure.faultinjection.FaultInjector;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.*;

import java.util.Map;

@RestController
@RequestMapping("/api/payment")
@RequiredArgsConstructor
public class PaymentController {

    private final FaultInjector faultInjector;

    @PostMapping("/process")
    public Map<String, Object> processPayment(@RequestBody Map<String, Object> request) {
        faultInjector.simulateSlowResponse("downstream-payment-timeout", () -> {});
        faultInjector.simulateException("downstream-payment-5xx", "SERVICE_UNAVAILABLE");

        return Map.of(
            "success", true,
            "transactionId", "TXN-" + System.currentTimeMillis(),
            "message", "Payment processed"
        );
    }

    @GetMapping("/status/{transactionId}")
    public Map<String, Object> getPaymentStatus(@PathVariable String transactionId) {
        faultInjector.simulateException("http-connection-pool-exhausted", "CONNECTION_REFUSED");

        return Map.of(
            "transactionId", transactionId,
            "status", "COMPLETED"
        );
    }
}
