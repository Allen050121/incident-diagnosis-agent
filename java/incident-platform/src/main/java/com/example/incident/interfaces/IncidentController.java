package com.example.incident.interfaces;

import com.example.incident.domain.incident.Incident;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/v1/incidents")
public class IncidentController {

    @PostMapping
    public ResponseEntity<IncidentResponse> createIncident(@RequestBody IncidentRequest request) {
        // TODO: Implement actual incident creation and Redis Streams publishing
        IncidentResponse response = new IncidentResponse();
        response.setTaskId("TASK-" + System.currentTimeMillis());
        response.setStatus("QUEUED");
        response.setMessage("Incident created successfully");
        return ResponseEntity.ok(response);
    }

    static class IncidentRequest {
        private String service;
        private String endpoint;
        private String alertType;
        private Double value;
        private Double threshold;
        private String startedAt;

        // Getters and Setters
        public String getService() { return service; }
        public void setService(String service) { this.service = service; }
        public String getEndpoint() { return endpoint; }
        public void setEndpoint(String endpoint) { this.endpoint = endpoint; }
        public String getAlertType() { return alertType; }
        public void setAlertType(String alertType) { this.alertType = alertType; }
        public Double getValue() { return value; }
        public void setValue(Double value) { this.value = value; }
        public Double getThreshold() { return threshold; }
        public void setThreshold(Double threshold) { this.threshold = threshold; }
        public String getStartedAt() { return startedAt; }
        public void setStartedAt(String startedAt) { this.startedAt = startedAt; }
    }

    static class IncidentResponse {
        private String taskId;
        private String status;
        private String message;

        // Getters and Setters
        public String getTaskId() { return taskId; }
        public void setTaskId(String taskId) { this.taskId = taskId; }
        public String getStatus() { return status; }
        public void setStatus(String status) { this.status = status; }
        public String getMessage() { return message; }
        public void setMessage(String message) { this.message = message; }
    }
}
