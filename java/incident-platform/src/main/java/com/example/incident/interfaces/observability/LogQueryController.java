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
@RequestMapping("/internal/v1/logs")
public class LogQueryController {

    @PostMapping("/query")
    public LogQueryResponse queryLogs(@RequestBody LogQueryRequest request) {
        log.info("Querying logs: service={}, timeWindow={}-{}",
                request.getService(), request.getStartTime(), request.getEndTime());

        // Mock log data for MVP
        List<LogEntry> logs = List.of(
            LogEntry.builder()
                .timestamp(LocalDateTime.now().minusMinutes(5))
                .level("ERROR")
                .service(request.getService())
                .message("query execution exceeded threshold")
                .traceId("TRACE-" + System.currentTimeMillis())
                .build(),
            LogEntry.builder()
                .timestamp(LocalDateTime.now().minusMinutes(3))
                .level("WARN")
                .service(request.getService())
                .message("slow query detected: 1850ms")
                .traceId("TRACE-" + System.currentTimeMillis())
                .build()
        );

        return LogQueryResponse.builder()
            .logs(logs)
            .totalCount(2)
            .truncated(false)
            .errorStats(Map.of("ERROR", 1, "WARN", 1))
            .build();
    }

    @Data
    @Builder
    @NoArgsConstructor
    @AllArgsConstructor
    public static class LogQueryRequest {
        private String service;
        private String startTime;
        private String endTime;
        private String keyword;
        private String traceId;
        private int maxResults = 100;
    }

    @Data
    @Builder
    @NoArgsConstructor
    @AllArgsConstructor
    public static class LogQueryResponse {
        private List<LogEntry> logs;
        private int totalCount;
        private boolean truncated;
        private Map<String, Integer> errorStats;
    }

    @Data
    @Builder
    @NoArgsConstructor
    @AllArgsConstructor
    public static class LogEntry {
        private LocalDateTime timestamp;
        private String level;
        private String service;
        private String message;
        private String traceId;
    }
}
