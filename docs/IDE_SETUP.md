# IDE 配置指南 (IntelliJ IDEA + PyCharm)

## 前置条件

确保已安装:
- ✅ JDK 21 (`java -version`)
- ✅ Maven 3.9+ (`mvn -version`)
- ✅ Python 3.12+ (`python --version`)

## IntelliJ IDEA 配置

### 1. 导入项目

1. File → Open → 选择 `java/` 目录
2. IDEA 会自动识别为 Maven 项目
3. 等待 Maven 依赖下载完成

### 2. 检查模块配置

File → Project Structure → Modules:
- 确认 4 个模块正确识别:
  - incident-platform
  - order-service
  - inventory-service
  - payment-mock-service

### 3. 配置运行配置 (Run Configurations)

**创建 4 个 Spring Boot 运行配置:**

```
Name: incident-platform
Main class: com.example.incident.IncidentPlatformApplication
Module: incident-platform
Working directory: $MODULE_WORKING_DIR$
```

重复以上步骤为其他三个服务创建配置。

### 4. 验证编译

```bash
cd java
mvn clean compile
```

## PyCharm 配置

### 1. 导入项目

1. File → Open → 选择 `python/` 目录
2. 配置虚拟环境:
   ```bash
   cd python
   python -m venv venv
   source venv/bin/activate  # Windows: venv\Scripts\activate
   pip install -r requirements.txt
   ```

### 2. 配置解释器

File → Settings → Project → Python Interpreter:
- 选择刚创建的虚拟环境
- 确认依赖包已安装

### 3. 配置运行配置

```
Name: Python Agent
Script path: python/app/main.py
Module name: uvicorn
Parameters: app.main:app --reload --port 8000
Working directory: $ProjectFileDir$
```

## 环境变量配置 (两个 IDE 通用)

### 1. 复制配置文件

```bash
# Java 服务
cp java/incident-platform/src/main/resources/application.yml.example \
   java/incident-platform/src/main/resources/application.yml

# Python Agent
cp python/app/config.py.example python/app/config.py

# 环境变量模板
cp .env.example .env
```

### 2. 配置敏感信息

编辑 `.env` 文件,填写:
- `LLM_API_KEY` - 你的 LLM API Key (**不要提交到 Git**)
- `LLM_BASE_URL` - LLM API 地址
- 其他可选配置

### 3. IDEA/PyCharm 环境变量

Run → Edit Configurations → Environment Variables:
- 可以添加 `DOTENV_FILE=.env` 让应用自动加载

## Docker 配置

### 启动基础设施

```bash
docker-compose up -d mysql redis prometheus loki elasticsearch
```

### 验证服务

```bash
docker-compose ps
```

应该看到:
- MySQL (3306)
- Redis (6379)
- Prometheus (9090)
- Grafana (3000)
- Loki (3100)
- Elasticsearch (9200)

## 快速验证清单

### Java 服务验证

在 IDEA 中分别启动 4 个服务,访问:
- http://localhost:8080/actuator/health (incident-platform)
- http://localhost:8081/actuator/health (order-service)
- http://localhost:8082/actuator/health (inventory-service)
- http://localhost:8083/actuator/health (payment-mock-service)

应该返回 `{"status":"UP"}`

### Python Agent 验证

在 PyCharm 中启动,访问:
- http://localhost:8000/health

应该返回 `{"status":"healthy"}`

## 常见问题

### Maven 依赖下载慢

在 `~/.m2/settings.xml` 中配置国内镜像:
```xml
<mirror>
  <id>aliyun</id>
  <mirrorOf>central</mirrorOf>
  <url>https://maven.aliyun.com/repository/public</url>
</mirror>
```

### Python 依赖安装失败

使用国内镜像源:
```bash
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
```

### 端口被占用

修改各服务的 `application.yml` 中的 `server.port`,或停止占用端口的进程。

## Git 工作流

当前项目已配置:
- ✅ 远程仓库: `https://github.com/Allen050121/incident-diagnosis-agent.git`
- ✅ `.gitignore` 已过滤敏感文件和环境配置
- ✅ 初始代码已推送到 `master` 分支

### 提交规范

```bash
git add .
git commit -m "feat: add xxx feature"
git push
```

提交信息格式:
- `feat:` - 新功能
- `fix:` - Bug 修复
- `docs:` - 文档更新
- `refactor:` - 重构
- `test:` - 测试相关

## 下一步

1. 实现 12 个故障模板
2. 完善 LangGraph 工作流
3. 实现调查工具接口
4. 运行完整的诊断流程测试
