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
};

struct RequestFailure {
    RequestKind kind = RequestKind::HealthCheck;
    int httpStatus = 0;
    QString stableCode;
    QString userMessage;
    QString details;
    QByteArray rawBody;
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
    void fetchTask(const QString &taskId);
    void fetchTasks(int limit);
    void fetchResults(int limit);

signals:
    void healthChecked(const TaskModels::HealthResponse &health);
    void taskCreated(const TaskModels::TaskSummary &task);
    void taskFetched(const TaskModels::TaskDetail &task);
    void tasksFetched(const TaskModels::TaskListResponse &tasks);
    void resultsFetched(const TaskModels::ResultListResponse &results);
    void requestFailed(const RequestFailure &failure);

private:
    void sendGetRequest(RequestKind kind, const QUrl &url);
    void sendPostRequest(RequestKind kind, const QUrl &url, const QJsonObject &payload);
    void handleReply(RequestKind kind, class QNetworkReply *reply);
    void emitInvalidBaseUrlFailure(RequestKind kind, const QString &details);
    RequestFailure buildNetworkFailure(RequestKind kind, class QNetworkReply *reply, const QByteArray &body) const;
    RequestFailure buildHttpFailure(RequestKind kind, class QNetworkReply *reply, const QByteArray &body) const;
    RequestFailure buildParseFailure(RequestKind kind, class QNetworkReply *reply, const QByteArray &body, const QString &details) const;

    QUrl m_baseUrl;
    QNetworkAccessManager m_network;
};

Q_DECLARE_METATYPE(RequestKind)
Q_DECLARE_METATYPE(RequestFailure)

