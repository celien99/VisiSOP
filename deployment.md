# VisiSOP - Deployment

Deploy the project to [FastAPI Cloud](https://fastapicloud.com) with the included GitHub Actions workflow.

## Create the FastAPI Cloud Application

Create an application in FastAPI Cloud and set its [Application Directory](https://fastapicloud.com/docs/builds-and-deployments/application-directory/) to `backend`.

Connect a PostgreSQL database using the [Neon](https://fastapicloud.com/docs/integrations/neon-integration/) or [Supabase](https://fastapicloud.com/docs/integrations/supabase-integration/) integration. Both integrations configure a `DATABASE_URL` secret automatically. You can also configure `DATABASE_URL` manually for another PostgreSQL provider.

## Configure the Application

### Environment Variables

Add these [environment variables](https://fastapicloud.com/docs/builds-and-deployments/environment-variables/) to the FastAPI Cloud application:

* `PROJECT_NAME`: The name of the project, used in the API documentation.
* `FRONTEND_HOST`: The public URL of the application, such as the generated `https://your-app.fastapicloud.dev` URL or a custom domain.

To enable Sentry, configure `SENTRY_DSN`.

### Secrets

Add this required value and mark it as a secret:

* `DATABASE_URL`: The PostgreSQL connection URL, configured automatically when using a database integration.

## Configure Continuous Deployment

The included `.github/workflows/deploy.yml` workflow builds the frontend, applies database migrations, and deploys the application whenever changes are pushed to `master`. You can also run it manually from the **Actions** tab.

Log in to FastAPI Cloud and configure the [deploy token](https://fastapicloud.com/docs/advanced-features/deploy-tokens/) and application ID as GitHub repository secrets:

```bash
uv run fastapi login
uv run fastapi cloud setup-ci --secrets-only --app-id <your-app-id>
```

If the GitHub CLI is installed and authenticated, the command configures `FASTAPI_CLOUD_TOKEN` and `FASTAPI_CLOUD_APP_ID` automatically. Otherwise, it prints the values so you can add them in your repository under **Settings** > **Secrets and variables** > **Actions**.

In the repository's **Settings** > **Secrets and variables** > **Actions** page, add the `PROJECT_NAME` repository variable and the `DATABASE_URL` repository secret.

Use the same values configured in FastAPI Cloud. For `DATABASE_URL`, use the connection URL from your database provider. The database must be reachable from GitHub-hosted runners so the preparation step can connect to it.

The deployment workflow performs these steps:

1. Installs and builds the frontend into `backend/app/frontend`.
2. Runs `backend/scripts/prestart.sh` to apply database migrations.
3. Deploys the project with `uv run fastapi deploy`.

## URLs

Replace `your-app.fastapicloud.dev` with the URL of your FastAPI Cloud application.

Application (frontend and API): `https://your-app.fastapicloud.dev`

Interactive API docs: `https://your-app.fastapicloud.dev/docs`

## Docker Compose

For deployment to your own server, see the [Docker Compose deployment guide](./deployment-docker-compose.md).
