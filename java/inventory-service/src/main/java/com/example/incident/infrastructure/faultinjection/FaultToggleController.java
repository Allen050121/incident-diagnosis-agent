package com.example.incident.infrastructure.faultinjection;

import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.*;

import java.util.Map;

@RestController
@RequestMapping("/internal/v1/faults")
@RequiredArgsConstructor
public class FaultToggleController {

    private final FaultConfig faultConfig;

    @GetMapping
    public Map<String, FaultConfig.FaultToggle> getFaults() {
        return faultConfig.getToggles();
    }

    @PostMapping("/{faultId}/activate")
    public FaultConfig.FaultToggle activateFault(
            @PathVariable String faultId,
            @RequestBody(required = false) Map<String, Object> parameters) {
        FaultConfig.FaultToggle toggle = faultConfig.getOrCreate(faultId);
        toggle.setActive(true);
        if (parameters != null) {
            toggle.setParameters(parameters);
        }
        return toggle;
    }

    @PostMapping("/{faultId}/deactivate")
    public FaultConfig.FaultToggle deactivateFault(@PathVariable String faultId) {
        FaultConfig.FaultToggle toggle = faultConfig.getOrCreate(faultId);
        toggle.setActive(false);
        return toggle;
    }

    @PostMapping("/reset")
    public String resetAllFaults() {
        faultConfig.resetAll();
        return "All faults reset";
    }
}
