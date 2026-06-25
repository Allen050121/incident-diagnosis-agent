package com.example.incident.interfaces.observability;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.web.bind.annotation.*;

import java.util.List;
import java.util.Map;

@Slf4j
@RestController
@RequestMapping("/internal/v1/topology")
public class TopologyController {

    @GetMapping("/{service}")
    public TopologyResponse getTopology(@PathVariable String service) {
        log.info("Getting topology for service: {}", service);

        // Mock topology data
        List<ServiceDependency> dependencies = switch (service) {
            case "order-service" -> List.of(
                ServiceDependency.builder()
                    .service("inventory-service")
                    .type("HTTP")
                    .endpoint("/api/inventory")
                    .build(),
                ServiceDependency.builder()
                    .service("payment-mock-service")
                    .type("HTTP")
                    .endpoint("/api/payment/process")
                    .build(),
                ServiceDependency.builder()
                    .service("mysql")
                    .type("DATABASE")
                    .endpoint("192.168.85.66:3306/incident_db")
                    .build(),
                ServiceDependency.builder()
                    .service("redis")
                    .type("CACHE")
                    .endpoint("192.168.85.66:6379")
                    .build()
            );
            case "inventory-service" -> List.of(
                ServiceDependency.builder()
                    .service("mysql")
                    .type("DATABASE")
                    .endpoint("192.168.85.66:3306/incident_db")
                    .build(),
                ServiceDependency.builder()
                    .service("redis")
                    .type("CACHE")
                    .endpoint("192.168.85.66:6379")
                    .build()
            );
            case "payment-mock-service" -> List.of(
                ServiceDependency.builder()
                    .service("redis")
                    .type("CACHE")
                    .endpoint("192.168.85.66:6379")
                    .build()
            );
            default -> List.of();
        };

        return TopologyResponse.builder()
            .service(service)
            .dependencies(dependencies)
            .build();
    }

    @Data
    @Builder
    @NoArgsConstructor
    @AllArgsConstructor
    public static class TopologyResponse {
        private String service;
        private List<ServiceDependency> dependencies;
    }

    @Data
    @Builder
    @NoArgsConstructor
    @AllArgsConstructor
    public static class ServiceDependency {
        private String service;
        private String type;
        private String endpoint;
    }
}
