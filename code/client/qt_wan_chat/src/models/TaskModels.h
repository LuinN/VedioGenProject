#pragma once

#include <QDateTime>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QJsonParseError>
#include <QJsonValue>
#include <QList>
#include <QMetaType>
#include <QString>

namespace TaskModels {

struct HealthResponse {
    bool ok = false;
    QString service;
};

struct ApiErrorPayload {
    QString code;
    QString message;
};

struct TaskSummary {
    QString taskId;
    QString clientRequestId;
    QString mode;
    QString status;
    QString prompt;
    QString size;
    QString outputPath;
    QString inputImagePath;
    QString errorMessage;
    QString logPath;
    QString createTimeRaw;
    QString updateTimeRaw;
    QDateTime createTime;
    QDateTime updateTime;
};

struct TaskDetail : TaskSummary {
    bool outputExists = false;
    bool inputImageExists = false;
    QString statusMessage;
    int progressCurrent = -1;
    int progressTotal = -1;
    int progressPercent = -1;
    QString downloadUrl;
};

struct TaskListResponse {
    QList<TaskSummary> items;
    int total = 0;
    int limit = 0;
};

struct TaskDeleteResponse {
    QString taskId;
    bool deleted = false;
};

struct ResultItem {
    QString taskId;
    QString outputPath;
    QString createTimeRaw;
    QDateTime createTime;
    bool outputExists = false;
    QString downloadUrl;
};

struct ResultListResponse {
    QList<ResultItem> items;
    int total = 0;
    int limit = 0;
};

inline QDateTime parseTimestamp(const QString &raw)
{
    QDateTime parsed = QDateTime::fromString(raw, Qt::ISODateWithMs);
    if (!parsed.isValid()) {
        parsed = QDateTime::fromString(raw, Qt::ISODate);
    }
    return parsed;
}

inline QString jsonTypeName(const QJsonValue &value)
{
    switch (value.type()) {
    case QJsonValue::Null:
        return QStringLiteral("null");
    case QJsonValue::Bool:
        return QStringLiteral("bool");
    case QJsonValue::Double:
        return QStringLiteral("number");
    case QJsonValue::String:
        return QStringLiteral("string");
    case QJsonValue::Array:
        return QStringLiteral("array");
    case QJsonValue::Object:
        return QStringLiteral("object");
    case QJsonValue::Undefined:
        return QStringLiteral("undefined");
    }
    return QStringLiteral("unknown");
}

inline bool requireString(const QJsonObject &object, const QString &key, QString &target, QString &error)
{
    const QJsonValue value = object.value(key);
    if (value.isUndefined()) {
        error = QStringLiteral("Missing required field '%1'.").arg(key);
        return false;
    }
    if (!value.isString()) {
        error = QStringLiteral("Field '%1' must be a string, got %2.")
                    .arg(key, jsonTypeName(value));
        return false;
    }
    target = value.toString();
    return true;
}

inline bool requireNullableString(const QJsonObject &object, const QString &key, QString &target, QString &error)
{
    const QJsonValue value = object.value(key);
    if (value.isUndefined()) {
        error = QStringLiteral("Missing required field '%1'.").arg(key);
        return false;
    }
    if (value.isNull()) {
        target.clear();
        return true;
    }
    if (!value.isString()) {
        error = QStringLiteral("Field '%1' must be a string or null, got %2.")
                    .arg(key, jsonTypeName(value));
        return false;
    }
    target = value.toString();
    return true;
}

inline bool requireBool(const QJsonObject &object, const QString &key, bool &target, QString &error)
{
    const QJsonValue value = object.value(key);
    if (value.isUndefined()) {
        error = QStringLiteral("Missing required field '%1'.").arg(key);
        return false;
    }
    if (!value.isBool()) {
        error = QStringLiteral("Field '%1' must be a bool, got %2.")
                    .arg(key, jsonTypeName(value));
        return false;
    }
    target = value.toBool();
    return true;
}

inline bool requireInt(const QJsonObject &object, const QString &key, int &target, QString &error)
{
    const QJsonValue value = object.value(key);
    if (value.isUndefined()) {
        error = QStringLiteral("Missing required field '%1'.").arg(key);
        return false;
    }
    if (!value.isDouble()) {
        error = QStringLiteral("Field '%1' must be a number, got %2.")
                    .arg(key, jsonTypeName(value));
        return false;
    }
    target = value.toInt();
    return true;
}

inline bool readOptionalNullableString(const QJsonObject &object, const QString &key, QString &target, QString &error)
{
    const QJsonValue value = object.value(key);
    if (value.isUndefined() || value.isNull()) {
        target.clear();
        return true;
    }
    if (!value.isString()) {
        error = QStringLiteral("Field '%1' must be a string or null, got %2.")
                    .arg(key, jsonTypeName(value));
        return false;
    }
    target = value.toString();
    return true;
}

inline bool readOptionalNullableInt(const QJsonObject &object, const QString &key, int &target, QString &error)
{
    const QJsonValue value = object.value(key);
    if (value.isUndefined() || value.isNull()) {
        target = -1;
        return true;
    }
    if (!value.isDouble()) {
        error = QStringLiteral("Field '%1' must be a number or null, got %2.")
                    .arg(key, jsonTypeName(value));
        return false;
    }
    target = value.toInt();
    return true;
}

inline bool readOptionalNullableBool(const QJsonObject &object, const QString &key, bool &target, QString &error)
{
    const QJsonValue value = object.value(key);
    if (value.isUndefined() || value.isNull()) {
        target = false;
        return true;
    }
    if (!value.isBool()) {
        error = QStringLiteral("Field '%1' must be a bool or null, got %2.")
                    .arg(key, jsonTypeName(value));
        return false;
    }
    target = value.toBool();
    return true;
}

inline bool requireArray(const QJsonObject &object, const QString &key, QJsonArray &target, QString &error)
{
    const QJsonValue value = object.value(key);
    if (value.isUndefined()) {
        error = QStringLiteral("Missing required field '%1'.").arg(key);
        return false;
    }
    if (!value.isArray()) {
        error = QStringLiteral("Field '%1' must be an array, got %2.")
                    .arg(key, jsonTypeName(value));
        return false;
    }
    target = value.toArray();
    return true;
}

inline bool parseTaskSummaryObject(const QJsonObject &object, TaskSummary &target, QString &error)
{
    if (!requireString(object, QStringLiteral("task_id"), target.taskId, error)
        || !requireString(object, QStringLiteral("status"), target.status, error)
        || !requireString(object, QStringLiteral("prompt"), target.prompt, error)
        || !requireNullableString(object, QStringLiteral("output_path"), target.outputPath, error)
        || !requireNullableString(object, QStringLiteral("error_message"), target.errorMessage, error)
        || !requireString(object, QStringLiteral("log_path"), target.logPath, error)
        || !requireString(object, QStringLiteral("create_time"), target.createTimeRaw, error)
        || !requireString(object, QStringLiteral("update_time"), target.updateTimeRaw, error)) {
        return false;
    }

    if (!readOptionalNullableString(object, QStringLiteral("mode"), target.mode, error)
        || !readOptionalNullableString(object, QStringLiteral("size"), target.size, error)
        || !readOptionalNullableString(object, QStringLiteral("input_image_path"), target.inputImagePath, error)) {
        return false;
    }

    target.createTime = parseTimestamp(target.createTimeRaw);
    target.updateTime = parseTimestamp(target.updateTimeRaw);
    return true;
}

inline bool parseTaskDetailObject(const QJsonObject &object, TaskDetail &target, QString &error)
{
    if (!parseTaskSummaryObject(object, target, error)
        || !requireBool(object, QStringLiteral("output_exists"), target.outputExists, error)
        || !readOptionalNullableBool(object, QStringLiteral("input_image_exists"), target.inputImageExists, error)
        || !readOptionalNullableString(object, QStringLiteral("status_message"), target.statusMessage, error)
        || !readOptionalNullableInt(object, QStringLiteral("progress_current"), target.progressCurrent, error)
        || !readOptionalNullableInt(object, QStringLiteral("progress_total"), target.progressTotal, error)
        || !readOptionalNullableInt(object, QStringLiteral("progress_percent"), target.progressPercent, error)
        || !readOptionalNullableString(object, QStringLiteral("download_url"), target.downloadUrl, error)) {
        return false;
    }
    return true;
}

inline bool parseResultItemObject(const QJsonObject &object, ResultItem &target, QString &error)
{
    if (!requireString(object, QStringLiteral("task_id"), target.taskId, error)
        || !requireString(object, QStringLiteral("output_path"), target.outputPath, error)
        || !requireString(object, QStringLiteral("create_time"), target.createTimeRaw, error)
        || !requireBool(object, QStringLiteral("output_exists"), target.outputExists, error)
        || !readOptionalNullableString(object, QStringLiteral("download_url"), target.downloadUrl, error)) {
        return false;
    }

    target.createTime = parseTimestamp(target.createTimeRaw);
    return true;
}

inline bool parseHealthResponse(const QJsonDocument &document, HealthResponse &target, QString &error)
{
    if (!document.isObject()) {
        error = QStringLiteral("Health response root must be a JSON object.");
        return false;
    }

    const QJsonObject object = document.object();
    if (!requireBool(object, QStringLiteral("ok"), target.ok, error)
        || !requireString(object, QStringLiteral("service"), target.service, error)) {
        return false;
    }
    return true;
}

inline bool parseTaskSummaryResponse(const QJsonDocument &document, TaskSummary &target, QString &error)
{
    if (!document.isObject()) {
        error = QStringLiteral("Task response root must be a JSON object.");
        return false;
    }
    return parseTaskSummaryObject(document.object(), target, error);
}

inline bool parseTaskDetailResponse(const QJsonDocument &document, TaskDetail &target, QString &error)
{
    if (!document.isObject()) {
        error = QStringLiteral("Task detail response root must be a JSON object.");
        return false;
    }
    return parseTaskDetailObject(document.object(), target, error);
}

inline bool parseTaskListResponse(const QJsonDocument &document, TaskListResponse &target, QString &error)
{
    if (!document.isObject()) {
        error = QStringLiteral("Task list response root must be a JSON object.");
        return false;
    }

    const QJsonObject object = document.object();
    QJsonArray items;
    if (!requireArray(object, QStringLiteral("items"), items, error)
        || !requireInt(object, QStringLiteral("total"), target.total, error)
        || !requireInt(object, QStringLiteral("limit"), target.limit, error)) {
        return false;
    }

    target.items.clear();
    target.items.reserve(items.size());
    for (int index = 0; index < items.size(); ++index) {
        if (!items.at(index).isObject()) {
            error = QStringLiteral("Task list item %1 must be a JSON object.").arg(index);
            return false;
        }

        TaskSummary item;
        if (!parseTaskSummaryObject(items.at(index).toObject(), item, error)) {
            error = QStringLiteral("Task list item %1: %2").arg(index).arg(error);
            return false;
        }
        target.items.append(item);
    }
    return true;
}

inline bool parseTaskDeleteResponse(const QJsonDocument &document, TaskDeleteResponse &target, QString &error)
{
    if (!document.isObject()) {
        error = QStringLiteral("Task delete response root must be a JSON object.");
        return false;
    }

    const QJsonObject object = document.object();
    if (!requireString(object, QStringLiteral("task_id"), target.taskId, error)
        || !requireBool(object, QStringLiteral("deleted"), target.deleted, error)) {
        return false;
    }
    return true;
}

inline bool parseResultListResponse(const QJsonDocument &document, ResultListResponse &target, QString &error)
{
    if (!document.isObject()) {
        error = QStringLiteral("Result list response root must be a JSON object.");
        return false;
    }

    const QJsonObject object = document.object();
    QJsonArray items;
    if (!requireArray(object, QStringLiteral("items"), items, error)
        || !requireInt(object, QStringLiteral("total"), target.total, error)
        || !requireInt(object, QStringLiteral("limit"), target.limit, error)) {
        return false;
    }

    target.items.clear();
    target.items.reserve(items.size());
    for (int index = 0; index < items.size(); ++index) {
        if (!items.at(index).isObject()) {
            error = QStringLiteral("Result list item %1 must be a JSON object.").arg(index);
            return false;
        }

        ResultItem item;
        if (!parseResultItemObject(items.at(index).toObject(), item, error)) {
            error = QStringLiteral("Result list item %1: %2").arg(index).arg(error);
            return false;
        }
        target.items.append(item);
    }
    return true;
}

inline bool parseErrorResponse(const QByteArray &payload, ApiErrorPayload &target, QString &error)
{
    QJsonParseError parseError;
    const QJsonDocument document = QJsonDocument::fromJson(payload, &parseError);
    if (parseError.error != QJsonParseError::NoError) {
        error = QStringLiteral("Failed to parse error JSON: %1").arg(parseError.errorString());
        return false;
    }
    if (!document.isObject()) {
        error = QStringLiteral("Error response root must be a JSON object.");
        return false;
    }

    const QJsonValue errorValue = document.object().value(QStringLiteral("error"));
    if (!errorValue.isObject()) {
        error = QStringLiteral("Error response must contain an 'error' object.");
        return false;
    }

    const QJsonObject errorObject = errorValue.toObject();
    if (!requireString(errorObject, QStringLiteral("code"), target.code, error)
        || !requireString(errorObject, QStringLiteral("message"), target.message, error)) {
        return false;
    }
    return true;
}

} // namespace TaskModels

Q_DECLARE_METATYPE(TaskModels::HealthResponse)
Q_DECLARE_METATYPE(TaskModels::TaskSummary)
Q_DECLARE_METATYPE(TaskModels::TaskDetail)
Q_DECLARE_METATYPE(TaskModels::TaskListResponse)
Q_DECLARE_METATYPE(TaskModels::TaskDeleteResponse)
Q_DECLARE_METATYPE(TaskModels::ResultItem)
Q_DECLARE_METATYPE(TaskModels::ResultListResponse)
