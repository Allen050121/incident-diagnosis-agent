package com.example.incident.interfaces;

import com.example.incident.infrastructure.faultinjection.FaultInjector;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.*;

import java.util.List;
import java.util.Map;

@RestController
@RequestMapping("/api/inventory")
@RequiredArgsConstructor
public class InventoryController {

    private final FaultInjector faultInjector;

    @GetMapping
    public List<Map<String, Object>> getInventory() {
        faultInjector.simulateSlowResponse("redis-hot-key", () -> {});

        return List.of(
            Map.of(
                "productId", "PROD-001",
                "productName", "Laptop",
                "quantity", 100,
                "price", 5999.00
            ),
            Map.of(
                "productId", "PROD-002",
                "productName", "Mouse",
                "quantity", 500,
                "price", 99.00
            )
        );
    }

    @GetMapping("/{productId}")
    public Map<String, Object> getInventoryByProduct(@PathVariable String productId) {
        faultInjector.simulateException("redis-timeout", "TIMEOUT");

        return Map.of(
            "productId", productId,
            "productName", "Laptop",
            "quantity", 100,
            "price", 5999.00
        );
    }

    @PostMapping("/deduct")
    public Map<String, Object> deductInventory(@RequestBody Map<String, Object> request) {
        faultInjector.simulateSlowResponse("thread-pool-exhausted", () -> {});

        return Map.of(
            "success", true,
            "message", "Inventory deducted"
        );
    }
}
