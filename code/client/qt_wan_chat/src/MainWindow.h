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
#include <QStringList>

class QEvent;
class QLineEdit;
class QLabel;
class QListWidget;
class QDialog;
class QFrame;
class QProgressBar;
class QPushButton;
class QScrollArea;
class QSplitter;
class QStatusBar;
class QTableWidget;
class QTimer;
class QVBoxLayout;

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

struct TaskProgressCard {
    QWidget *container = nullptr;
    QLabel *titleLabel = nullptr;
    QLabel *statusLabel = nullptr;
    QLabel *stageLabel = nullptr;
    QLabel *metaLabel = nullptr;
    QLabel *timeLabel = nullptr;
    QLabel *errorLabel = nullptr;
    QProgressBar *progressBar = nullptr;
};

struct TaskProgressTiming {
    QDateTime firstObservedAt;
    double lastRatio = -1.0;
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
    void showConfigurationDialog();
    void showVideosDialog();
    void showDiagnosticsDialog();
    void chooseInputImage();
    void removeInputImage();
    void chooseDownloadDirectory();
    void deleteSelectedTask();
    void downloadSelectedResult();
    void openSelectedOutputDirectory();
    void playSelectedVideo();
    void deleteSelectedVideo();

    void onHealthChecked(const TaskModels::HealthResponse &health);
    void onCapabilitiesFetched(const TaskModels::CapabilityListResponse &capabilities);
    void onTaskCreated(const TaskModels::TaskSummary &task);
    void onTaskFetched(const TaskModels::TaskDetail &task);
    void onTasksFetched(const TaskModels::TaskListResponse &tasks);
    void onTaskDeleted(const TaskModels::TaskDeleteResponse &task);
    void onResultsFetched(const TaskModels::ResultListResponse &results);
    void onResultDownloaded(const ResultDownload &download);
    void onRequestFailed(const RequestFailure &failure);

protected:
    bool eventFilter(QObject *watched, QEvent *event) override;

private:
    static constexpr int kPollIntervalMs = 2000;
    static constexpr int kListLimit = 20;

    void setupUi();
    QWidget *buildTasksPanel();
    QWidget *buildChatPanel();
    QWidget *buildConfigPanel();
    QWidget *buildVideosPanel();
    QWidget *buildDiagnosticsPanel();
    void setupDialogs();
    void setupHiddenResultsTable();
    void connectSignals();
    void applyVisualStyle();
    void refreshProfileOptions();
    void refreshSizeOptions(const QString &preferredProfileId = {});
    QString selectedProfileId() const;
    QString effectiveProfileIdForCurrentRequest() const;
    QStringList allowedSizesForProfile(const QString &profileId) const;
    QString defaultSizeForProfile(const QString &profileId) const;
    QStringList supportedModesForProfile(const QString &profileId) const;
    bool isProfileAvailable(const QString &profileId, QString *reason = nullptr) const;

    void appendChatMessage(const QString &role, const QString &message);
    QWidget *appendChatWidget(QWidget *widget, bool alignRight);
    void scrollChatToBottom();
    void ensureTaskProgressCard(const TaskModels::TaskDetail &task);
    void updateTaskProgressCard(const TaskModels::TaskDetail &task);
    double taskProgressRatio(const TaskModels::TaskDetail &task) const;
    QString formatDuration(qint64 totalSeconds) const;
    QString formatTaskProgressTiming(const QString &taskId, const TaskModels::TaskDetail &task);
    void appendDiagnostic(const QString &message);
    void showUserNotice(const QString &message, int timeoutMs = 5000);
    void finishSmokeTest(bool success, const QString &summary);
    QString smokeTaskSnapshotSummary() const;

    void refreshTasksTable();
    QWidget *buildTaskCard(const TaskModels::TaskDetail &task);
    QWidget *buildTaskResultPreview(const TaskModels::TaskDetail &task);
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
    void loadDeletedTasks();
    void saveDeletedTasks();
    QString deletedTasksIndexPath() const;
    bool isDeletedTask(const QString &taskId) const;
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
    QString thumbnailPathForTask(const QString &taskId) const;
    QString thumbnailVersionPathForTask(const QString &taskId) const;
    bool isTaskThumbnailCurrent(const QString &taskId) const;
    void writeTaskThumbnailVersion(const QString &taskId);
    QString previewVideoPathForTask(const QString &taskId) const;
    QString localVideoPathForPreview(const QString &taskId) const;
    void ensureTaskResultPreview(const TaskModels::TaskDetail &task);
    bool startPreviewDownloadForTask(const TaskModels::TaskDetail &task, const QString &reason);
    void enqueueThumbnailGeneration(const QString &taskId);
    void startNextThumbnailGeneration();
    void finishThumbnailGeneration(bool success, const QString &details);
    void playTaskVideo(const QString &taskId);
    bool deleteTaskLocalData(const QString &taskId, QString *error = nullptr);
    bool removeTaskCacheDirectory(const QString &taskId, QStringList *preservedVideos = nullptr, QString *error = nullptr);
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
    QHash<QString, TaskModels::CapabilityProfile> m_capabilities;
    QHash<QString, TaskModels::TaskDetail> m_tasks;
    QHash<QString, TaskModels::ResultItem> m_results;
    QHash<QString, DownloadedVideo> m_downloadedVideos;
    QHash<QString, TaskLocalMetadata> m_taskMetadata;
    QHash<QString, InputImageAttachment> m_pendingImageRequests;
    QSet<QString> m_deletedTaskIds;
    QSet<QString> m_activeTaskIds;
    QSet<QString> m_inFlightTaskIds;
    QSet<QString> m_downloadInFlightTaskIds;
    QSet<QString> m_taskDeleteInFlightIds;
    QSet<QString> m_previewDownloadInFlightTaskIds;
    QSet<QString> m_thumbnailQueuedTaskIds;
    QSet<QString> m_thumbnailInFlightTaskIds;
    QSet<QString> m_thumbnailFailedTaskIds;
    QSet<QString> m_chatTerminalReportedTaskIds;
    QHash<QString, TaskProgressCard> m_taskProgressCards;
    QHash<QString, TaskProgressTiming> m_taskProgressTimings;
    QStringList m_thumbnailQueue;
    QString m_currentThumbnailTaskId;
    InputImageAttachment m_currentInputImage;

    QTimer *m_pollTimer = nullptr;
    QTimer *m_smokeTestTimeoutTimer = nullptr;
    bool m_smokeTestEnabled = false;
    bool m_smokeTestCompleted = false;
    bool m_smokeRequiresDownload = false;
    QString m_smokeImagePath;
    QString m_smokeTestTaskId;

    QDialog *m_configurationDialog = nullptr;
    QDialog *m_videosDialog = nullptr;
    QDialog *m_diagnosticsDialog = nullptr;
    QLineEdit *m_serviceUrlEdit = nullptr;
    QComboBox *m_profileCombo = nullptr;
    QComboBox *m_sizeCombo = nullptr;
    QLineEdit *m_wslDistroEdit = nullptr;
    QLineEdit *m_downloadDirectoryEdit = nullptr;
    QLineEdit *m_outputDirectoryEdit = nullptr;
    QPushButton *m_applyServiceUrlButton = nullptr;
    QPushButton *m_sendButton = nullptr;
    QPushButton *m_configurationButton = nullptr;
    QPushButton *m_videosButton = nullptr;
    QPushButton *m_diagnosticsButton = nullptr;
    QPushButton *m_addImageButton = nullptr;
    QPushButton *m_removeImageButton = nullptr;
    QPushButton *m_deleteTaskButton = nullptr;
    QPushButton *m_chooseDownloadDirectoryButton = nullptr;
    QPushButton *m_downloadSelectedButton = nullptr;
    QPushButton *m_openOutputDirectoryButton = nullptr;
    QPushButton *m_playVideoButton = nullptr;
    QPushButton *m_deleteVideoButton = nullptr;
    QScrollArea *m_chatScrollArea = nullptr;
    QWidget *m_chatContent = nullptr;
    QVBoxLayout *m_chatLayout = nullptr;
    QPlainTextEdit *m_promptEdit = nullptr;
    QWidget *m_inputImagePreview = nullptr;
    QLabel *m_inputImageThumbnail = nullptr;
    QLabel *m_inputImageNameLabel = nullptr;
    QPlainTextEdit *m_diagnosticLog = nullptr;
    QListWidget *m_tasksList = nullptr;
    QTableWidget *m_resultsTable = nullptr;
    QTableWidget *m_videosTable = nullptr;
};
