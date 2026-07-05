# StudentHub — AWS DevOps CI/CD Project

Flask app → Docker → ECR → ECS Fargate → ALB → RDS, deployed automatically
on every `git push` via CodePipeline + CodeBuild, with CloudWatch monitoring
and SNS alerts.

Use this alongside the code files in this folder: `app.py`, `templates/index.html`,
`requirements.txt`, `Dockerfile`, `buildspec.yml`, `taskdef.json`.

---

## Day 1 — IAM + VPC

### 1.1 Create an IAM admin user (never work as root)
- Console → **IAM** → Users → **Create user**
- Username: `devops-admin`
- Check **Provide user access to AWS Management Console**
- Set a custom password, uncheck "must create new password"
- **Attach policies directly** → `AdministratorAccess` → Create user
- Save the console sign-in URL shown after creation

### 1.2 Enable MFA
- Click the `devops-admin` user → **Security credentials** tab
- **Assign MFA device** → use Google Authenticator (or similar) on your phone

### 1.3 Create CLI access keys
- Same tab → **Access keys** → **Create access key**
- Use case: Command Line Interface (CLI)
- Download the `.csv` and store it somewhere safe (never commit it to Git)

### 1.4 Switch off root
- Log out of the root account. From now on, log in as `devops-admin`.

### 1.5 Create the VPC
- Console → **VPC** → **Create VPC**
- Select **VPC and more** (auto-creates subnets/routing for you)
- Name tag: `studenthub-vpc`
- IPv4 CIDR: `10.0.0.0/16`
- Number of AZs: `2`
- Public subnets: `2`, Private subnets: `2`
- NAT Gateways: **None** (keeps this free — add for a real production setup)
- VPC endpoints: None → **Create VPC**

You now have 2 public subnets (for the ALB), 2 private subnets (for RDS/ECS),
an Internet Gateway, and route tables — all wired automatically.

---

## Day 2 — RDS + Flask app running locally

### 2.1 Security group for RDS
- VPC Console → **Security Groups** → **Create security group**
- Name: `rds-sg`, VPC: `studenthub-vpc`
- Inbound rule: Type `PostgreSQL`, Port `5432`, Source: your IP for now
  (you'll restrict this to the ECS security group once it exists)

### 2.2 Create the RDS instance
- Console → **RDS** → **Create database**
- Method: Standard create · Engine: PostgreSQL · Version: 15.x
- Template: **Free tier**
- DB instance identifier: `studenthub-db`
- Master username: `dbadmin` · Master password: choose something strong
- Instance class: `db.t3.micro` · Storage: 20 GB gp2
- VPC: `studenthub-vpc` · Create new subnet group
- **Public access: No** (important — RDS should never be public)
- Security group: `rds-sg`
- Initial database name: `studenthub`
- Create database — takes 5–10 minutes to become "Available"

### 2.3 Run the Flask app locally
```bash
cd studenthub
python -m venv venv
source venv/bin/activate        # venv\Scripts\activate on Windows
pip install -r requirements.txt

export DB_HOST=<your-rds-endpoint>
export DB_NAME=studenthub
export DB_USER=dbadmin
export DB_PASSWORD=<your-password>

python app.py
```
Visit `http://localhost:5000` — you should see "StudentHub is LIVE" and
"Database status: Connected". If it says "Connection failed", double check
your RDS security group allows your current IP on port 5432.

### 2.4 Push to GitHub
```bash
git init
git add .
git commit -m "Initial StudentHub app"
git branch -M main
git remote add origin https://github.com/<yourname>/studenthub.git
git push -u origin main
```

---

## Day 3 — Docker + ECR + ECS Fargate

### 3.1 Test the Docker image locally
```bash
docker build -t studenthub-app .
docker run -p 5000:5000 \
  -e DB_HOST=<rds-endpoint> -e DB_NAME=studenthub \
  -e DB_USER=dbadmin -e DB_PASSWORD=<password> \
  studenthub-app
```
Visit `http://localhost:5000` again to confirm the containerized app works.

### 3.2 Create the ECR repository
- Console → **ECR** → **Create repository**
- Visibility: Private · Name: `studenthub-app` → Create
- Note the URI, e.g. `123456789012.dkr.ecr.us-east-1.amazonaws.com/studenthub-app`

### 3.3 Push your image manually (first time only — CodeBuild automates this later)
```bash
aws ecr get-login-password --region <region> | \
  docker login --username AWS --password-stdin <ECR_URI>

docker tag studenthub-app:latest <ECR_URI>:latest
docker push <ECR_URI>:latest
```

### 3.4 Create the ECS cluster
- Console → **ECS** → **Create Cluster**
- Name: `studenthub-cluster` · Infrastructure: **AWS Fargate** → Create

### 3.5 Create the task definition
- Use `taskdef.json` in this folder as your template — replace
  `<ACCOUNT_ID>`, `<ECR_URI>`, `<RDS_ENDPOINT>`, and `<REGION>` with your real
  values, then either paste it in via the console's JSON editor or register
  it via CLI:
  ```bash
  aws ecs register-task-definition --cli-input-json file://taskdef.json
  ```
- Store the DB password in **Secrets Manager** (`studenthub-db-password`)
  rather than hardcoding it — the task definition already references it.

### 3.6 Create the ECS service + ALB
- Cluster → **Services** tab → **Create**
- Launch type: Fargate · Task definition: `studenthub-task`
- Service name: `studenthub-service` · Desired tasks: `1`
- VPC: `studenthub-vpc` · Subnets: the two **private** subnets
- Security group: create `ecs-sg`, allow port 5000 from the ALB's security group
- Load balancer: **Application Load Balancer**
  - Create new: `studenthub-alb`, listener HTTP:80
  - Target group: `studenthub-tg`, port 5000, health check path `/health`
- Create Service

Once healthy, the ALB's DNS name is your public URL.

---

## Day 4 — CodeBuild (build & test in isolation)

### 4.1 `buildspec.yml`
Already included in this folder — CodeBuild reads it automatically.

### 4.2 Create the CodeBuild project
- Console → **CodeBuild** → **Create build project**
- Name: `studenthub-build`
- Source: GitHub → connect and select your `studenthub` repo
- Environment: image `aws/codebuild/standard:7.0`
  - ✅ Enable **Privileged** (required to build Docker images)
  - Let it auto-create a new service role
- Environment variables (Plaintext is fine for URI/name; use Secrets Manager
  for anything sensitive):
  - `ECR_URI` = your ECR repository URI
  - `ECR_REPO_NAME` = `studenthub-app`
  - `AWS_REGION` = your region, e.g. `us-east-1`
- Buildspec: **Use a buildspec file** (it'll find `buildspec.yml` in the repo root)
- Artifacts: Amazon S3 → create bucket `studenthub-artifacts`
- Create build project

### 4.3 Grant ECR permissions
- IAM → Roles → find `codebuild-studenthub-build-service-role`
- Add permissions → attach `AmazonEC2ContainerRegistryPowerUser`

### 4.4 Test it standalone
- CodeBuild project → **Start build**
- Confirm in the logs: image builds, pushes to ECR, and
  `imagedefinitions.json` is written — all **before** wiring up CodePipeline,
  so you know this stage works in isolation.

---

## Day 5 — CodePipeline + CloudWatch + SNS + full end-to-end test

### 5.1 Create the pipeline
- Console → **CodePipeline** → **Create pipeline**
- Name: `studenthub-pipeline` · New service role (auto-created)
- Artifact store: S3 → `studenthub-artifacts`

**Stage 1 — Source**
- Provider: GitHub (Version 2) → connect/authorize
- Repository: `studenthub` · Branch: `main`

**Stage 2 — Build**
- Provider: AWS CodeBuild · Project: `studenthub-build`

**Stage 3 — Deploy**
- Provider: Amazon ECS
- Cluster: `studenthub-cluster` · Service: `studenthub-service`
- Image definitions file: `imagedefinitions.json`

Create pipeline — it runs immediately.

### 5.2 CloudWatch dashboard
- Console → **CloudWatch** → **Dashboards** → **Create dashboard**
- Name: `StudentHub-Dashboard`
- Add widgets: ECS CPU utilization, ECS memory utilization, ALB request count,
  RDS database connections

### 5.3 SNS alerts
- Console → **SNS** → **Topics** → **Create topic** (Standard)
- Name: `studenthub-alerts`
- Create subscription: Protocol `Email`, your email address
- Confirm the subscription from the email you receive

### 5.4 CloudWatch alarm
- CloudWatch → **Alarms** → **Create alarm**
- Metric: ECS → `studenthub-cluster` → CPUUtilization
- Threshold: greater than 80%
- Action: notify `studenthub-alerts`
- Name: `High-CPU-Alert`

### 5.5 Full end-to-end demo (this is the part to show your evaluator)
1. Change something in `app.py` on your laptop (e.g. edit the homepage message).
2. `git add . && git commit -m "Update homepage"`
3. `git push origin main`
4. Open CodePipeline in the console — it triggers automatically within seconds.
5. Watch the **Build** stage: CodeBuild builds the new image and pushes to ECR.
6. Watch the **Deploy** stage: ECS performs a rolling deployment — old tasks
   stay up until new ones pass the `/health` check, so there's zero downtime.
7. Refresh the ALB URL — your change is live, with no manual deploy step.

---

## Notes / gotchas worth knowing before you present this

- **RDS must stay private** — "Public access: No" is not optional; it's the
  single most common security mistake in student AWS projects.
- **Health check path** (`/health`) matters — if the ALB target group checks
  `/` instead and your DB connection is briefly down, ECS will kill healthy
  containers thinking they're unhealthy.
- **Secrets Manager, not plaintext env vars**, for the DB password — this is
  an easy thing to point out in a viva/demo as a security best practice you
  deliberately followed.
- **Cost control**: Fargate + ALB + NAT Gateway (if you add one later) are the
  main things that cost money beyond free tier. Delete the ECS service, ALB,
  and RDS instance when you're done demoing to avoid surprise charges.
