package com.example.incident.interfaces.observability;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.web.bind.annotation.*;

import java.time.LocalDateTime;
import java.util.List;
import java.util.Map;

@Slf4j
@RestController
@RequestMapping("/internal/v1/metrics")
public class MetricsQueryController {

    @PostMapping("/query")
    public MetricsQueryResponse queryMetrics(@RequestBody MetricsQueryRequest request) {
        log.info("Querying metrics: service={}, metric={}", request.getService(), request.getMetric());

        // Mock metrics data for MVP
        MetricData data = MetricData.builder()
            .metric(request.getMetric())
            .window("10m")
            .baseline(0.42)
            .peak(1.0)
            .current(0.95)
            .anomalyStart(LocalDateTime.now().minusMinutes(5))
            .build();

        return MetricsQueryResponse.builder()
            .data(data)
            .timestamp(LocalDateTime.now())
            .build();
    }

    @Data
    @Builder
    @NoArgsConstructor
    @AllArgsConstructor
    public static class MetricsQueryRequest {
        private String service;
        private String metric;
        private String startTime;
        private String endTime;
    }

    @Data
    @Builder
    @NoArgsConstructor
    @AllArgsConstructor
    public static class MetricsQueryResponse {
        private MetricData data;
        private LocalDateTime timestamp;
    }

    @Data
    @Builder
    @NoArgsConstructor
    @AllArgsConstructor
    public static class MetricData {
        private String metric;
        private String window;
        private double baseline;
        private double peak;
        private double current;
        private LocalDateTime anomalyStart;
    }
}
