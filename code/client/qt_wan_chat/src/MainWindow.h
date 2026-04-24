#pragma once

#include "ApiClient.h"
#include "models/TaskModels.h"

#include <QComboBox>
#include <QDateTime>
#include <QHash>
#include <QMainWindow>
#include <QPlainTextEdit>
#include <QPointer>
#include <QSet>

class QLineEdit;
class QLabel;
class QListWidget;
class QPushButton;
class QSplitter;
class QStatusBar;
class QTableWidget;
class QTextBrowser;
class QTimer;

struct DownloadedVideo {
    QString taskId;
    QString prompt;
    QString localPath;
    QString downloadUrl;
    QString sourceOutputPath;
    QString createTimeRaw;
    QString downloadedAtRaw;
    QDateTime createTime;
    QDateTime downloadedAt;
    qint64 fileSize = 0;
};

struct InputImageAttachment {
    QString clientRequestId;
    QString sourcePath;
    QString cachedPath;
    QString pendingDirectory;
    QString fileName;
    QString extension;
    qint64 fileSize = 0;
};

struct TaskLocalMetadata {
    QString taskId;
    QString clientRequestId;
    QString prompt;
    QString mode;
    QString inputImageLocalPath;
    QString inputImageServerPath;
    QString createTimeRaw;
    QDateTime createTime;
    bool hasInputImage = false;
};

class MainWindow : public QMainWindow
{
    Q_OBJECT

public:
    explicit MainWindow(QWidget *parent = nullptr);
    void startSmokeTest(const QString &prompt, int timeoutMs = 60 * 60 * 1000, const QString &downloadDirectory = {}, const QString &imagePath = {});
    void startTaskMonitorSmoke(const QString &taskId, int timeoutMs = 60 * 60 * 1000, const QString &downloadDirectory = {});
    bool setDownloadDirectory(const QString &directory, QString *error = nullptr);

signals:
    void smokeTestFinished(bool success, const QString &summary);

private slots:
    void applyServiceUrl();
    void sendPrompt();
    void refreshInitialData();
    void pollActiveTasks();
    void updateOutputDirectoryField();
    void chooseInputImage();
    void removeInputImage();
    void chooseDownloadDirectory();
    void downloadSelectedResult();
    void openSelectedOutputDirectory();
    void playSelectedVideo();

    void onHealthChecked(const TaskModels::HealthResponse &health);
    void onTaskCreated(const TaskModels::TaskSummary &task);
    void onTaskFetched(const TaskModels::TaskDetail &task);
    void onTasksFetched(const TaskModels::TaskListResponse &tasks);
    void onResultsFetched(const TaskModels::ResultListResponse &results);
    void onResultDownloaded(const ResultDownload &download);
    void onRequestFailed(const RequestFailure &failure);

private:
    static constexpr int kPollIntervalMs = 2000;
    static constexpr int kListLimit = 20;

    void setupUi();
    QWidget *buildTasksPanel();
    QWidget *buildChatPanel();
    QWidget *buildConfigPanel();
    void connectSignals();
    void applyVisualStyle();

    void appendChatMessage(const QString &role, const QString &message);
    void appendDiagnostic(const QString &message);
    void showUserNotice(const QString &message, int timeoutMs = 5000);
    void finishSmokeTest(bool success, const QString &summary);
    QString smokeTaskSnapshotSummary() const;

    void refreshTasksTable();
    QWidget *buildTaskCard(const TaskModels::TaskDetail &task);
    void refreshResultsTable();
    void refreshVideosTable();
    void syncTaskSummary(const TaskModels::TaskSummary &task);
    void syncTaskDetail(const TaskModels::TaskDetail &task);
    void syncResultItem(const TaskModels::ResultItem &result);
    void syncDownloadedVideo(const DownloadedVideo &video);

    QString selectedTaskId() const;
    QString selectedResultTaskId() const;
    QString selectedVideoTaskId() const;
    QString currentSelectedOutputPath() const;
    QString currentSelectedOutputDirectory(QString *error = nullptr) const;
    bool isTerminalStatus(const QString &status) const;
    void startPollingIfNeeded();
    void stopPollingIfIdle();
    void loadPersistentState();
    void loadDownloadedVideos();
    void saveDownloadedVideos();
    QString videoIndexPath() const;
    void loadTaskMetadata();
    void saveTaskMetadata(const TaskLocalMetadata &metadata);
    bool restoreTaskMetadataFromFile(const QString &metadataPath);
    QString tasksCacheRoot() const;
    QString taskCacheDirectory(const QString &taskId) const;
    QString pendingTaskCacheDirectory(const QString &clientRequestId) const;
    QString taskMetadataPath(const QString &taskId) const;
    QString metadataPathForDirectory(const QString &directory) const;
    bool prepareInputImageAttachment(const QString &sourcePath, InputImageAttachment &attachment, QString *error = nullptr);
    bool validateInputImagePath(const QString &sourcePath, QString &extension, qint64 &fileSize, QString *error = nullptr) const;
    bool setCurrentInputImage(const QString &sourcePath, QString *error = nullptr);
    void clearCurrentInputImage(bool removeCachedFile);
    void updateInputImagePreview();
    bool finalizePendingImageForTask(const TaskModels::TaskSummary &task, TaskLocalMetadata &metadata, QString *error = nullptr);
    QString taskReferenceImagePath(const TaskModels::TaskDetail &task) const;
    QString taskModeLabel(const TaskModels::TaskDetail &task) const;
    QString configuredDownloadDirectory() const;
    bool ensureDownloadDirectory(QString &directory);
    bool startResultDownloadForTask(const TaskModels::TaskDetail &task, const QString &reason);
    bool startResultDownloadForResult(const TaskModels::ResultItem &result, const QString &reason);
    QString localVideoPathForTask(const QString &taskId) const;
    QString downloadUrlForTaskId(const QString &taskId) const;
    QString promptForTaskId(const QString &taskId) const;
    QString createTimeRawForTaskId(const QString &taskId) const;
    QDateTime createTimeForTaskId(const QString &taskId) const;

    TaskModels::TaskDetail summaryToDetail(const TaskModels::TaskSummary &task) const;
    QString formatTimestamp(const QDateTime &dateTime, const QString &fallback) const;

    ApiClient m_apiClient;
    QHash<QString, TaskModels::TaskDetail> m_tasks;
    QHash<QString, TaskModels::ResultItem> m_results;
    QHash<QString, DownloadedVideo> m_downloadedVideos;
    QHash<QString, TaskLocalMetadata> m_taskMetadata;
    QHash<QString, InputImageAttachment> m_pendingImageRequests;
    QSet<QString> m_activeTaskIds;
    QSet<QString> m_inFlightTaskIds;
    QSet<QString> m_downloadInFlightTaskIds;
    InputImageAttachment m_currentInputImage;

    QTimer *m_pollTimer = nullptr;
    QTimer *m_smokeTestTimeoutTimer = nullptr;
    bool m_smokeTestEnabled = false;
    bool m_smokeTestCompleted = false;
    bool m_smokeRequiresDownload = false;
    QString m_smokeImagePath;
    QString m_smokeTestTaskId;

    QLineEdit *m_serviceUrlEdit = nullptr;
    QComboBox *m_sizeCombo = nullptr;
    QLineEdit *m_wslDistroEdit = nullptr;
    QLineEdit *m_downloadDirectoryEdit = nullptr;
    QLineEdit *m_outputDirectoryEdit = nullptr;
    QPushButton *m_applyServiceUrlButton = nullptr;
    QPushButton *m_sendButton = nullptr;
    QPushButton *m_addImageButton = nullptr;
    QPushButton *m_removeImageButton = nullptr;
    QPushButton *m_chooseDownloadDirectoryButton = nullptr;
    QPushButton *m_downloadSelectedButton = nullptr;
    QPushButton *m_openOutputDirectoryButton = nullptr;
    QPushButton *m_playVideoButton = nullptr;
    QTextBrowser *m_chatView = nullptr;
    QPlainTextEdit *m_promptEdit = nullptr;
    QWidget *m_inputImagePreview = nullptr;
    QLabel *m_inputImageThumbnail = nullptr;
    QLabel *m_inputImageNameLabel = nullptr;
    QPlainTextEdit *m_diagnosticLog = nullptr;
    QListWidget *m_tasksList = nullptr;
    QTableWidget *m_resultsTable = nullptr;
    QTableWidget *m_videosTable = nullptr;
};
