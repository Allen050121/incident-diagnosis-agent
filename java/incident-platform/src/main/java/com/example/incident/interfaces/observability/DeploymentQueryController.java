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
@RequestMapping("/internal/v1/deployments")
public class DeploymentQueryController {

    @PostMapping("/query")
    public DeploymentQueryResponse queryDeployments(@RequestBody DeploymentQueryRequest request) {
        log.info("Querying deployments: service={}", request.getService());

        List<DeploymentInfo> deployments = List.of(
            DeploymentInfo.builder()
                .version("v1.2.3")
                .deployedAt(LocalDateTime.now().minusHours(2))
                .gitCommit("abc1234")
                .deployer("yangjw")
                .changes("Fixed order processing bug")
                .build(),
            DeploymentInfo.builder()
                .version("v1.2.2")
                .deployedAt(LocalDateTime.now().minusDays(1))
                .gitCommit("def5678")
                .deployer("yangjw")
                .changes("Updated inventory service")
                .build()
        );

        return DeploymentQueryResponse.builder()
            .deployments(deployments)
            .build();
    }

    @Data
    @Builder
    @NoArgsConstructor
    @AllArgsConstructor
    public static class DeploymentQueryRequest {
        private String service;
        private String startTime;
        private String endTime;
        private int maxResults = 10;
    }

    @Data
    @Builder
    @NoArgsConstructor
    @AllArgsConstructor
    public static class DeploymentQueryResponse {
        private List<DeploymentInfo> deployments;
    }

    @Data
    @Builder
    @NoArgsConstructor
    @AllArgsConstructor
    public static class DeploymentInfo {
        private String version;
        private LocalDateTime deployedAt;
        private String gitCommit;
        private String deployer;
        private String changes;
    }
}
