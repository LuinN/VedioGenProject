#include "ApiClient.h"

#include <QJsonDocument>
#include <QFile>
#include <QFileInfo>
#include <QHttpMultiPart>
#include <QNetworkReply>
#include <QNetworkRequest>
#include <QSaveFile>
#include <QUrlQuery>

namespace {

constexpr int kSuccessStatusLowerBound = 200;
constexpr int kSuccessStatusUpperBound = 300;

QUrl normalizedBaseUrl(const QUrl &input)
{
    QUrl url = input;
    url.setQuery(QString());
    url.setFragment(QString());
    url.setPath(QStringLiteral("/"));
    return url;
}

QString responseSnippet(const QByteArray &body)
{
    const QString text = QString::fromUtf8(body).simplified();
    if (text.size() <= 240) {
        return text;
    }
    return text.left(240) + QStringLiteral("...");
}

QString mimeTypeForImagePath(const QString &path)
{
    const QString suffix = QFileInfo(path).suffix().toLower();
    if (suffix == QStringLiteral("png")) {
        return QStringLiteral("image/png");
    }
    if (suffix == QStringLiteral("jpg") || suffix == QStringLiteral("jpeg")) {
        return QStringLiteral("image/jpeg");
    }
    if (suffix == QStringLiteral("webp")) {
        return QStringLiteral("image/webp");
    }
    return QStringLiteral("application/octet-stream");
}

} // namespace

QString requestKindName(RequestKind kind)
{
    switch (kind) {
    case RequestKind::HealthCheck:
        return QStringLiteral("GET /healthz");
    case RequestKind::CreateTask:
        return QStringLiteral("POST /api/tasks");
    case RequestKind::FetchTask:
        return QStringLiteral("GET /api/tasks/{task_id}");
    case RequestKind::FetchTasks:
        return QStringLiteral("GET /api/tasks");
    case RequestKind::DeleteTask:
        return QStringLiteral("DELETE /api/tasks/{task_id}");
    case RequestKind::FetchResults:
        return QStringLiteral("GET /api/results");
    case RequestKind::DownloadResult:
        return QStringLiteral("GET /api/results/{task_id}/file");
    }
    return QStringLiteral("Unknown request");
}

ApiClient::ApiClient(QObject *parent)
    : QObject(parent)
{
}

bool ApiClient::setBaseUrlString(const QString &baseUrl, QString *error)
{
    const QUrl parsed = QUrl::fromUserInput(baseUrl.trimmed());
    if (!parsed.isValid() || parsed.scheme().isEmpty() || parsed.host().isEmpty()) {
        if (error != nullptr) {
            *error = QStringLiteral("Invalid service URL: %1").arg(baseUrl.trimmed());
        }
        return false;
    }

    m_baseUrl = normalizedBaseUrl(parsed);
    if (error != nullptr) {
        error->clear();
    }
    return true;
}

QUrl ApiClient::baseUrl() const
{
    return m_baseUrl;
}

void ApiClient::checkHealth()
{
    if (!m_baseUrl.isValid()) {
        emitInvalidBaseUrlFailure(RequestKind::HealthCheck, QStringLiteral("Service base URL is not configured."));
        return;
    }

    QUrl url = m_baseUrl;
    url.setPath(QStringLiteral("/healthz"));
    sendGetRequest(RequestKind::HealthCheck, url);
}

void ApiClient::createImageTask(const QString &prompt, const QString &size, const QString &localImagePath, const QString &clientRequestId)
{
    if (!m_baseUrl.isValid()) {
        emitInvalidBaseUrlFailure(RequestKind::CreateTask, QStringLiteral("Service base URL is not configured."));
        return;
    }

    QUrl url = m_baseUrl;
    url.setPath(QStringLiteral("/api/tasks"));
    sendMultipartCreateTask(url, prompt, size, localImagePath, clientRequestId);
}

void ApiClient::fetchTask(const QString &taskId)
{
    if (!m_baseUrl.isValid()) {
        emitInvalidBaseUrlFailure(RequestKind::FetchTask, QStringLiteral("Service base URL is not configured."));
        return;
    }

    QUrl url = m_baseUrl;
    url.setPath(QStringLiteral("/api/tasks/%1").arg(taskId));
    sendGetRequest(RequestKind::FetchTask, url);
}

void ApiClient::fetchTasks(int limit)
{
    if (!m_baseUrl.isValid()) {
        emitInvalidBaseUrlFailure(RequestKind::FetchTasks, QStringLiteral("Service base URL is not configured."));
        return;
    }

    QUrl url = m_baseUrl;
    url.setPath(QStringLiteral("/api/tasks"));
    QUrlQuery query;
    query.addQueryItem(QStringLiteral("limit"), QString::number(limit));
    url.setQuery(query);
    sendGetRequest(RequestKind::FetchTasks, url);
}

void ApiClient::deleteTask(const QString &taskId)
{
    const QString trimmedTaskId = taskId.trimmed();
    if (trimmedTaskId.isEmpty()) {
        RequestFailure failure;
        failure.kind = RequestKind::DeleteTask;
        failure.stableCode = QStringLiteral("invalid_task_id");
        failure.userMessage = QStringLiteral("Task id is empty.");
        emit requestFailed(failure);
        return;
    }
    if (!m_baseUrl.isValid()) {
        emitInvalidBaseUrlFailure(RequestKind::DeleteTask, QStringLiteral("Service base URL is not configured."));
        return;
    }

    QUrl url = m_baseUrl;
    url.setPath(QStringLiteral("/api/tasks/%1").arg(trimmedTaskId));
    sendDeleteRequest(RequestKind::DeleteTask, url, trimmedTaskId);
}

void ApiClient::fetchResults(int limit)
{
    if (!m_baseUrl.isValid()) {
        emitInvalidBaseUrlFailure(RequestKind::FetchResults, QStringLiteral("Service base URL is not configured."));
        return;
    }

    QUrl url = m_baseUrl;
    url.setPath(QStringLiteral("/api/results"));
    QUrlQuery query;
    query.addQueryItem(QStringLiteral("limit"), QString::number(limit));
    url.setQuery(query);
    sendGetRequest(RequestKind::FetchResults, url);
}

void ApiClient::downloadResult(const QString &taskId, const QUrl &downloadUrl, const QString &localPath, const QString &purpose)
{
    if (taskId.trimmed().isEmpty()) {
        emitInvalidBaseUrlFailure(RequestKind::DownloadResult, QStringLiteral("Task id is empty."));
        return;
    }
    if (!downloadUrl.isValid() || downloadUrl.scheme().isEmpty() || downloadUrl.host().isEmpty()) {
        RequestFailure failure;
        failure.kind = RequestKind::DownloadResult;
        failure.taskId = taskId.trimmed();
        failure.downloadPurpose = purpose.trimmed();
        failure.stableCode = QStringLiteral("invalid_download_url");
        failure.userMessage = QStringLiteral("The result download URL is invalid.");
        failure.details = downloadUrl.toString();
        failure.url = downloadUrl;
        emit requestFailed(failure);
        return;
    }
    if (localPath.trimmed().isEmpty()) {
        RequestFailure failure;
        failure.kind = RequestKind::DownloadResult;
        failure.taskId = taskId.trimmed();
        failure.downloadPurpose = purpose.trimmed();
        failure.stableCode = QStringLiteral("invalid_local_path");
        failure.userMessage = QStringLiteral("The local save path is empty.");
        failure.url = downloadUrl;
        emit requestFailed(failure);
        return;
    }

    QNetworkRequest request(downloadUrl);
    request.setRawHeader("Accept", "video/mp4");

    QNetworkReply *reply = m_network.get(request);
    reply->setProperty("taskId", taskId.trimmed());
    reply->setProperty("localPath", localPath.trimmed());
    reply->setProperty("downloadPurpose", purpose.trimmed());
    connect(reply, &QNetworkReply::finished, this, [this, reply]() {
        handleReply(RequestKind::DownloadResult, reply);
    });
}

void ApiClient::sendGetRequest(RequestKind kind, const QUrl &url)
{
    QNetworkRequest request(url);
    request.setHeader(QNetworkRequest::ContentTypeHeader, QStringLiteral("application/json; charset=utf-8"));
    request.setRawHeader("Accept", "application/json");

    QNetworkReply *reply = m_network.get(request);
    connect(reply, &QNetworkReply::finished, this, [this, kind, reply]() {
        handleReply(kind, reply);
    });
}

void ApiClient::sendDeleteRequest(RequestKind kind, const QUrl &url, const QString &taskId)
{
    QNetworkRequest request(url);
    request.setRawHeader("Accept", "application/json");

    QNetworkReply *reply = m_network.deleteResource(request);
    reply->setProperty("taskId", taskId.trimmed());
    connect(reply, &QNetworkReply::finished, this, [this, kind, reply]() {
        handleReply(kind, reply);
    });
}

void ApiClient::sendMultipartCreateTask(const QUrl &url, const QString &prompt, const QString &size, const QString &localImagePath, const QString &clientRequestId)
{
    const QString trimmedPath = localImagePath.trimmed();
    QFile file(trimmedPath);
    if (!file.open(QIODevice::ReadOnly)) {
        const QString details = QStringLiteral("Failed to open image for upload: %1 | path=%2")
                                    .arg(file.errorString(), trimmedPath);
        emitLocalFailure(
            RequestKind::CreateTask,
            QStringLiteral("image_upload_open_failed"),
            QStringLiteral("The selected image could not be opened for upload."),
            details,
            url,
            clientRequestId);
        return;
    }
    const QByteArray imageBody = file.readAll();
    if (imageBody.isEmpty() && file.size() > 0) {
        emitLocalFailure(
            RequestKind::CreateTask,
            QStringLiteral("image_upload_read_failed"),
            QStringLiteral("The selected image could not be read for upload."),
            QStringLiteral("Failed to read image bytes: %1 | path=%2").arg(file.errorString(), trimmedPath),
            url,
            clientRequestId);
        return;
    }

    auto *multipart = new QHttpMultiPart(QHttpMultiPart::FormDataType);

    auto appendTextPart = [multipart](const QString &name, const QString &value) {
        QHttpPart part;
        part.setHeader(QNetworkRequest::ContentDispositionHeader, QStringLiteral("form-data; name=\"%1\"").arg(name));
        part.setBody(value.toUtf8());
        multipart->append(part);
    };

    appendTextPart(QStringLiteral("mode"), QStringLiteral("i2v"));
    appendTextPart(QStringLiteral("prompt"), prompt);
    appendTextPart(QStringLiteral("size"), size);

    QHttpPart imagePart;
    QString fileName = QFileInfo(trimmedPath).fileName();
    fileName.replace(QLatin1Char('"'), QLatin1Char('_'));
    imagePart.setHeader(
        QNetworkRequest::ContentDispositionHeader,
        QStringLiteral("form-data; name=\"image\"; filename=\"%1\"").arg(fileName));
    imagePart.setHeader(QNetworkRequest::ContentTypeHeader, mimeTypeForImagePath(trimmedPath));
    imagePart.setBody(imageBody);
    multipart->append(imagePart);

    QNetworkRequest request(url);
    request.setRawHeader("Accept", "application/json");

    QNetworkReply *reply = m_network.post(request, multipart);
    multipart->setParent(reply);
    reply->setProperty("clientRequestId", clientRequestId.trimmed());
    connect(reply, &QNetworkReply::finished, this, [this, reply]() {
        handleReply(RequestKind::CreateTask, reply);
    });
}

void ApiClient::handleReply(RequestKind kind, QNetworkReply *reply)
{
    const QByteArray body = reply->readAll();
    const int statusCode = reply->attribute(QNetworkRequest::HttpStatusCodeAttribute).toInt();

    if (statusCode == 0 && reply->error() != QNetworkReply::NoError) {
        emit requestFailed(buildNetworkFailure(kind, reply, body));
        reply->deleteLater();
        return;
    }

    if (statusCode < kSuccessStatusLowerBound || statusCode >= kSuccessStatusUpperBound) {
        emit requestFailed(buildHttpFailure(kind, reply, body));
        reply->deleteLater();
        return;
    }

    if (kind == RequestKind::DownloadResult) {
        const QString localPath = reply->property("localPath").toString();
        QSaveFile file(localPath);
        if (!file.open(QIODevice::WriteOnly)) {
            emit requestFailed(
                buildDownloadSaveFailure(
                    reply,
                    body,
                    QStringLiteral("Failed to open local file for writing: %1").arg(file.errorString())));
            reply->deleteLater();
            return;
        }
        if (file.write(body) != body.size()) {
            emit requestFailed(
                buildDownloadSaveFailure(
                    reply,
                    body,
                    QStringLiteral("Failed to write complete video file: %1").arg(file.errorString())));
            reply->deleteLater();
            return;
        }
        if (!file.commit()) {
            emit requestFailed(
                buildDownloadSaveFailure(
                    reply,
                    body,
                    QStringLiteral("Failed to commit local video file: %1").arg(file.errorString())));
            reply->deleteLater();
            return;
        }

        ResultDownload download;
        download.taskId = reply->property("taskId").toString();
        download.localPath = localPath;
        download.purpose = reply->property("downloadPurpose").toString();
        download.fileSize = body.size();
        download.url = reply->request().url();
        emit resultDownloaded(download);
        reply->deleteLater();
        return;
    }

    QJsonParseError parseError;
    const QJsonDocument document = QJsonDocument::fromJson(body, &parseError);
    if (parseError.error != QJsonParseError::NoError) {
        emit requestFailed(
            buildParseFailure(
                kind,
                reply,
                body,
                QStringLiteral("JSON parse failed: %1").arg(parseError.errorString())));
        reply->deleteLater();
        return;
    }

    QString error;
    switch (kind) {
    case RequestKind::HealthCheck: {
        TaskModels::HealthResponse health;
        if (!TaskModels::parseHealthResponse(document, health, error)) {
            emit requestFailed(buildParseFailure(kind, reply, body, error));
            break;
        }
        emit healthChecked(health);
        break;
    }
    case RequestKind::CreateTask: {
        TaskModels::TaskSummary task;
        if (!TaskModels::parseTaskSummaryResponse(document, task, error)) {
            emit requestFailed(buildParseFailure(kind, reply, body, error));
            break;
        }
        task.clientRequestId = reply->property("clientRequestId").toString();
        emit taskCreated(task);
        break;
    }
    case RequestKind::FetchTask: {
        TaskModels::TaskDetail task;
        if (!TaskModels::parseTaskDetailResponse(document, task, error)) {
            emit requestFailed(buildParseFailure(kind, reply, body, error));
            break;
        }
        emit taskFetched(task);
        break;
    }
    case RequestKind::FetchTasks: {
        TaskModels::TaskListResponse tasks;
        if (!TaskModels::parseTaskListResponse(document, tasks, error)) {
            emit requestFailed(buildParseFailure(kind, reply, body, error));
            break;
        }
        emit tasksFetched(tasks);
        break;
    }
    case RequestKind::DeleteTask: {
        TaskModels::TaskDeleteResponse task;
        if (!TaskModels::parseTaskDeleteResponse(document, task, error)) {
            emit requestFailed(buildParseFailure(kind, reply, body, error));
            break;
        }
        emit taskDeleted(task);
        break;
    }
    case RequestKind::FetchResults: {
        TaskModels::ResultListResponse results;
        if (!TaskModels::parseResultListResponse(document, results, error)) {
            emit requestFailed(buildParseFailure(kind, reply, body, error));
            break;
        }
        emit resultsFetched(results);
        break;
    }
    }

    reply->deleteLater();
}

void ApiClient::emitInvalidBaseUrlFailure(RequestKind kind, const QString &details)
{
    RequestFailure failure;
    failure.kind = kind;
    failure.stableCode = QStringLiteral("invalid_base_url");
    failure.userMessage = QStringLiteral("The service URL is invalid. Please update the configuration.");
    failure.details = details;
    failure.url = m_baseUrl;
    emit requestFailed(failure);
}

void ApiClient::emitLocalFailure(RequestKind kind, const QString &stableCode, const QString &userMessage, const QString &details, const QUrl &url, const QString &clientRequestId)
{
    RequestFailure failure;
    failure.kind = kind;
    failure.clientRequestId = clientRequestId;
    failure.stableCode = stableCode;
    failure.userMessage = userMessage;
    failure.details = details;
    failure.url = url;
    emit requestFailed(failure);
}

RequestFailure ApiClient::buildNetworkFailure(RequestKind kind, QNetworkReply *reply, const QByteArray &body) const
{
    RequestFailure failure;
    failure.kind = kind;
    failure.httpStatus = 0;
    failure.taskId = reply->property("taskId").toString();
    failure.clientRequestId = reply->property("clientRequestId").toString();
    failure.downloadPurpose = reply->property("downloadPurpose").toString();
    failure.stableCode = QStringLiteral("network_error");
    failure.userMessage = QStringLiteral("Could not reach the local service. Check the URL and make sure FastAPI is running.");
    failure.details = reply->errorString();
    failure.rawBody = body;
    failure.url = reply->request().url();
    return failure;
}

RequestFailure ApiClient::buildHttpFailure(RequestKind kind, QNetworkReply *reply, const QByteArray &body) const
{
    RequestFailure failure;
    failure.kind = kind;
    failure.httpStatus = reply->attribute(QNetworkRequest::HttpStatusCodeAttribute).toInt();
    failure.taskId = reply->property("taskId").toString();
    failure.clientRequestId = reply->property("clientRequestId").toString();
    failure.downloadPurpose = reply->property("downloadPurpose").toString();
    failure.rawBody = body;
    failure.url = reply->request().url();

    TaskModels::ApiErrorPayload apiError;
    QString parseError;
    if (TaskModels::parseErrorResponse(body, apiError, parseError)) {
        failure.stableCode = apiError.code;
        failure.userMessage = apiError.message;
        failure.details = QStringLiteral("HTTP %1").arg(failure.httpStatus);
        return failure;
    }

    failure.stableCode = QStringLiteral("http_error");
    failure.userMessage = QStringLiteral("The service returned HTTP %1 for %2.")
                              .arg(failure.httpStatus)
                              .arg(requestKindName(kind));
    failure.details = parseError;
    const QString snippet = responseSnippet(body);
    if (!snippet.isEmpty()) {
        if (!failure.details.isEmpty()) {
            failure.details += QStringLiteral(" | ");
        }
        failure.details += QStringLiteral("body=%1").arg(snippet);
    }
    return failure;
}

RequestFailure ApiClient::buildParseFailure(RequestKind kind, QNetworkReply *reply, const QByteArray &body, const QString &details) const
{
    RequestFailure failure;
    failure.kind = kind;
    failure.httpStatus = reply->attribute(QNetworkRequest::HttpStatusCodeAttribute).toInt();
    failure.taskId = reply->property("taskId").toString();
    failure.clientRequestId = reply->property("clientRequestId").toString();
    failure.downloadPurpose = reply->property("downloadPurpose").toString();
    failure.stableCode = QStringLiteral("client_parse_error");
    failure.userMessage = QStringLiteral("The service returned malformed JSON for %1.")
                              .arg(requestKindName(kind));
    failure.details = details;
    const QString snippet = responseSnippet(body);
    if (!snippet.isEmpty()) {
        failure.details += QStringLiteral(" | body=%1").arg(snippet);
    }
    failure.rawBody = body;
    failure.url = reply->request().url();
    return failure;
}

RequestFailure ApiClient::buildDownloadSaveFailure(QNetworkReply *reply, const QByteArray &body, const QString &details) const
{
    RequestFailure failure;
    failure.kind = RequestKind::DownloadResult;
    failure.httpStatus = reply->attribute(QNetworkRequest::HttpStatusCodeAttribute).toInt();
    failure.taskId = reply->property("taskId").toString();
    failure.downloadPurpose = reply->property("downloadPurpose").toString();
    failure.stableCode = QStringLiteral("download_save_error");
    failure.userMessage = QStringLiteral("The result video could not be saved locally.");
    failure.details = details;
    failure.rawBody = body;
    failure.url = reply->request().url();
    return failure;
}
