#pragma once

#include "models/TaskModels.h"

#include <QByteArray>
#include <QNetworkAccessManager>
#include <QObject>
#include <QUrl>

enum class RequestKind {
    HealthCheck,
    CreateTask,
    FetchTask,
    FetchTasks,
    FetchResults,
    DownloadResult,
};

struct RequestFailure {
    RequestKind kind = RequestKind::HealthCheck;
    int httpStatus = 0;
    QString clientRequestId;
    QString stableCode;
    QString userMessage;
    QString details;
    QByteArray rawBody;
    QUrl url;
};

struct ResultDownload {
    QString taskId;
    QString localPath;
    qint64 fileSize = 0;
    QUrl url;
};

QString requestKindName(RequestKind kind);

class ApiClient : public QObject
{
    Q_OBJECT

public:
    explicit ApiClient(QObject *parent = nullptr);

    bool setBaseUrlString(const QString &baseUrl, QString *error = nullptr);
    QUrl baseUrl() const;

    void checkHealth();
    void createTask(const QString &prompt, const QString &size);
    void createImageTask(const QString &prompt, const QString &size, const QString &localImagePath, const QString &clientRequestId);
    void fetchTask(const QString &taskId);
    void fetchTasks(int limit);
    void fetchResults(int limit);
    void downloadResult(const QString &taskId, const QUrl &downloadUrl, const QString &localPath);

signals:
    void healthChecked(const TaskModels::HealthResponse &health);
    void taskCreated(const TaskModels::TaskSummary &task);
    void taskFetched(const TaskModels::TaskDetail &task);
    void tasksFetched(const TaskModels::TaskListResponse &tasks);
    void resultsFetched(const TaskModels::ResultListResponse &results);
    void resultDownloaded(const ResultDownload &download);
    void requestFailed(const RequestFailure &failure);

private:
    void sendGetRequest(RequestKind kind, const QUrl &url);
    void sendPostRequest(RequestKind kind, const QUrl &url, const QJsonObject &payload);
    void sendMultipartCreateTask(const QUrl &url, const QString &prompt, const QString &size, const QString &localImagePath, const QString &clientRequestId);
    void handleReply(RequestKind kind, class QNetworkReply *reply);
    void emitInvalidBaseUrlFailure(RequestKind kind, const QString &details);
    void emitLocalFailure(RequestKind kind, const QString &stableCode, const QString &userMessage, const QString &details, const QUrl &url = {}, const QString &clientRequestId = {});
    RequestFailure buildNetworkFailure(RequestKind kind, class QNetworkReply *reply, const QByteArray &body) const;
    RequestFailure buildHttpFailure(RequestKind kind, class QNetworkReply *reply, const QByteArray &body) const;
    RequestFailure buildParseFailure(RequestKind kind, class QNetworkReply *reply, const QByteArray &body, const QString &details) const;
    RequestFailure buildDownloadSaveFailure(class QNetworkReply *reply, const QByteArray &body, const QString &details) const;

    QUrl m_baseUrl;
    QNetworkAccessManager m_network;
};

Q_DECLARE_METATYPE(RequestKind)
Q_DECLARE_METATYPE(RequestFailure)
Q_DECLARE_METATYPE(ResultDownload)
