package com.example.incident.domain.incident;

import org.junit.jupiter.api.Test;
import java.time.LocalDateTime;
import static org.junit.jupiter.api.Assertions.*;

class IncidentTest {

    @Test
    void shouldCreateIncidentWithDefaults() {
        Incident incident = new Incident();
        incident.setIncidentId("INC-001");
        incident.setService("order-service");
        incident.setAlertType("P95_LATENCY_HIGH");
        incident.setValue(5000.0);
        incident.setThreshold(1000.0);
        incident.setStartedAt(LocalDateTime.now());

        assertEquals("INC-001", incident.getIncidentId());
        assertEquals("order-service", incident.getService());
        assertEquals("P95_LATENCY_HIGH", incident.getAlertType());
        assertEquals(5000.0, incident.getValue());
        assertEquals(1000.0, incident.getThreshold());
        assertEquals("OPEN", incident.getStatus());
    }

    @Test
    void shouldUpdateStatus() {
        Incident incident = new Incident();
        incident.setStatus("INVESTIGATING");
        assertEquals("INVESTIGATING", incident.getStatus());

        incident.setStatus("DIAGNOSED");
        assertEquals("DIAGNOSED", incident.getStatus());
    }

    @Test
    void shouldHandleNullableFields() {
        Incident incident = new Incident();
        assertNull(incident.getEndpoint());
        assertNull(incident.getEndedAt());

        incident.setEndpoint("/api/orders");
        assertEquals("/api/orders", incident.getEndpoint());
    }

    @Test
    void shouldHandleAllAlertTypes() {
        Incident incident = new Incident();

        incident.setAlertType("P95_LATENCY_HIGH");
        assertEquals("P95_LATENCY_HIGH", incident.getAlertType());

        incident.setAlertType("ERROR_RATE_HIGH");
        assertEquals("ERROR_RATE_HIGH", incident.getAlertType());

        incident.setAlertType("THROUGHPUT_LOW");
        assertEquals("THROUGHPUT_LOW", incident.getAlertType());

        incident.setAlertType("MQ_LAG_HIGH");
        assertEquals("MQ_LAG_HIGH", incident.getAlertType());
    }

    @Test
    void shouldHandleAllStatuses() {
        Incident incident = new Incident();
        String[] statuses = {"OPEN", "QUEUED", "INVESTIGATING", "DIAGNOSED", "INCONCLUSIVE", "FAILED", "CANCELLED"};

        for (String status : statuses) {
            incident.setStatus(status);
            assertEquals(status, incident.getStatus());
        }
    }
}
