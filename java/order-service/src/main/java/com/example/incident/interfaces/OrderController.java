package com.example.incident.interfaces;

import com.example.incident.infrastructure.faultinjection.FaultInjector;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.*;

import java.time.LocalDateTime;
import java.util.List;
import java.util.Map;

@RestController
@RequestMapping("/api/orders")
@RequiredArgsConstructor
public class OrderController {

    private final FaultInjector faultInjector;

    @GetMapping
    public List<Map<String, Object>> getOrders() {
        return faultInjector.simulateSlowResponse("mysql-slow-query", () ->
            List.of(
                Map.of(
                    "orderId", "ORD-001",
                    "product", "Laptop",
                    "quantity", 1,
                    "price", 5999.00,
                    "status", "COMPLETED",
                    "createdAt", LocalDateTime.now().toString()
                )
            )
        );
    }

    @GetMapping("/{id}")
    public Map<String, Object> getOrder(@PathVariable String id) {
        faultInjector.simulateException("mysql-connection-pool-exhausted", "TIMEOUT");

        return Map.of(
            "orderId", id,
            "product", "Laptop",
            "quantity", 1,
            "price", 5999.00,
            "status", "COMPLETED"
        );
    }

    @PostMapping
    public Map<String, Object> createOrder(@RequestBody Map<String, Object> order) {
        faultInjector.simulateSlowResponse("redis-timeout", () -> {});

        return Map.of(
            "orderId", "ORD-" + System.currentTimeMillis(),
            "status", "CREATED",
            "message", "Order created successfully"
        );
    }
}
