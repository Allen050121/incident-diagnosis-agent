package com.example.incident.infrastructure.faultinjection;

import lombok.Data;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.context.annotation.Configuration;

import java.util.HashMap;
import java.util.Map;

@Data
@Configuration
@ConfigurationProperties(prefix = "fault")
public class FaultConfig {

    private boolean enabled = true;

    private Map<String, FaultToggle> toggles = new HashMap<>();

    @Data
    public static class FaultToggle {
        private boolean active = false;
        private Map<String, Object> parameters = new HashMap<>();
    }

    public void resetAll() {
        toggles.values().forEach(toggle -> toggle.setActive(false));
    }

    public FaultToggle getOrCreate(String faultId) {
        return toggles.computeIfAbsent(faultId, k -> new FaultToggle());
    }
}
