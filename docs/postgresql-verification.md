# PostgreSQL本地验收

2026-11-17，在Windows上运行PostgreSQL 17.12官方分发二进制，完成真实数据库迁移和后端回归。开发预览采用SQLite，PostgreSQL实验使用独立临时集群。

## 组件来源

PostgreSQL官网的Windows下载页指向EDB安装器及免安装二进制包。本次使用17.12的Windows x64 ZIP，文件为386,263,884字节，下载件SHA256为a2cd8a774389347b70be7748ac4a37ef43cb6ee539c5fc3e85ae264b15e4a04c。该摘要来自本次HTTPS下载，用于固定复跑所用归档。[PostgreSQL官方Windows入口](https://www.postgresql.org/download/windows/)、[EDB二进制入口](https://www.enterprisedb.com/download-postgresql-binaries)

prepare_postgres.py把归档及bin/lib/share解压到忽略目录data/postgresql-17.12，校验摘要并检查归档路径范围。组件用于开发验收，发布容器仍按Compose的postgres:17-alpine配置另行验收。

## 复跑

安装requirements-dev.txt后，在项目根目录执行。下载包约368MiB，需要网络，首次解压和初始化需要额外磁盘空间。

```powershell
.\.venv\Scripts\python.exe scripts/prepare_postgres.py
.\.venv\Scripts\python.exe scripts/postgres_check.py
```

脚本每次创建test-results/postgres-*集群，随机数据库名与密码，采用SCRAM-SHA-256认证，仅监听127.0.0.1的临时端口，以当前用户启动。控制程序采用隐藏窗口和文件输出，处理Windows子进程继承输出句柄的行为。

测试环境通过GALSTUDY_TEST_DATABASE_URL选择新建的galstudy_test_*数据库。conftest核对数据库类型和名称，默认回归仍使用独立SQLite库，测试中模型和图片生成采用Demo/Mock。结束时停止临时集群并删除临时密码文件，保留集群及日志供排查。结果写入postgresql-test-result.txt和postgresql-result.json。

## 实际发现与修复

首次真实PostgreSQL回归出现4项失败，聊天插入报integer out of range。消息使用time.time_ns()，迁移003已声明BIGINT，ORM隐式整数类型仍使psycopg把参数转换为INTEGER。现将ChatMessage.created_at明确映射为SQLAlchemy BigInteger，沿用已有表结构。

修复后，同一46项后端回归在SQLite和PostgreSQL均通过。PostgreSQL已执行迁移1至6并创建22张公开schema表，验证私有资料、故事与错题、聊天、云协议模拟、订单权益、并发占用与补偿。重复运行迁移后用户、课程、存档和聊天消息的行数与按ID排序的内容指纹保持一致，最终报告记录具体数量。所有临时服务在脚本结束时停止。

## 验收范围

证据覆盖Windows原生PostgreSQL 17.12、SQLAlchemy/psycopg、全部迁移和测试API路径。Linux容器镜像、Docker Compose网络/健康检查/持久卷、公开部署及目标负载仍待实际执行。基于Windows临时实例的结果不推算生产容量，发布环境另记录版本、备份恢复与运行参数。
