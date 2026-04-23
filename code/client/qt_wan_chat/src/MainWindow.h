#pragma once

#include "ApiClient.h"
#include "models/TaskModels.h"

#include <QComboBox>
#include <QHash>
#include <QMainWindow>
#include <QPlainTextEdit>
#include <QPointer>
#include <QSet>

class QLineEdit;
class QPushButton;
class QSplitter;
class QStatusBar;
class QTableWidget;
class QTextBrowser;
class QTimer;

class MainWindow : public QMainWindow
{
    Q_OBJECT

public:
    explicit MainWindow(QWidget *parent = nullptr);
    void startSmokeTest(const QString &prompt, int timeoutMs = 60000);

signals:
    void smokeTestFinished(bool success, const QString &summary);

private slots:
    void applyServiceUrl();
    void sendPrompt();
    void refreshInitialData();
    void pollActiveTasks();
    void updateOutputDirectoryField();
    void openSelectedOutputDirectory();

    void onHealthChecked(const TaskModels::HealthResponse &health);
    void onTaskCreated(const TaskModels::TaskSummary &task);
    void onTaskFetched(const TaskModels::TaskDetail &task);
    void onTasksFetched(const TaskModels::TaskListResponse &tasks);
    void onResultsFetched(const TaskModels::ResultListResponse &results);
    void onRequestFailed(const RequestFailure &failure);

private:
    static constexpr int kPollIntervalMs = 2000;
    static constexpr int kListLimit = 20;

    void setupUi();
    QWidget *buildTasksPanel();
    QWidget *buildChatPanel();
    QWidget *buildConfigPanel();
    void connectSignals();

    void appendChatMessage(const QString &role, const QString &message);
    void appendDiagnostic(const QString &message);
    void showUserNotice(const QString &message, int timeoutMs = 5000);
    void finishSmokeTest(bool success, const QString &summary);

    void refreshTasksTable();
    void refreshResultsTable();
    void syncTaskSummary(const TaskModels::TaskSummary &task);
    void syncTaskDetail(const TaskModels::TaskDetail &task);
    void syncResultItem(const TaskModels::ResultItem &result);

    QString selectedTaskId() const;
    QString selectedResultTaskId() const;
    QString currentSelectedOutputPath() const;
    QString currentSelectedOutputDirectory(QString *error = nullptr) const;
    bool isTerminalStatus(const QString &status) const;
    void startPollingIfNeeded();
    void stopPollingIfIdle();

    TaskModels::TaskDetail summaryToDetail(const TaskModels::TaskSummary &task) const;
    QString formatTimestamp(const QDateTime &dateTime, const QString &fallback) const;

    ApiClient m_apiClient;
    QHash<QString, TaskModels::TaskDetail> m_tasks;
    QHash<QString, TaskModels::ResultItem> m_results;
    QSet<QString> m_activeTaskIds;
    QSet<QString> m_inFlightTaskIds;

    QTimer *m_pollTimer = nullptr;
    QTimer *m_smokeTestTimeoutTimer = nullptr;
    bool m_smokeTestEnabled = false;
    bool m_smokeTestCompleted = false;
    QString m_smokeTestTaskId;

    QLineEdit *m_serviceUrlEdit = nullptr;
    QComboBox *m_sizeCombo = nullptr;
    QLineEdit *m_wslDistroEdit = nullptr;
    QLineEdit *m_outputDirectoryEdit = nullptr;
    QPushButton *m_applyServiceUrlButton = nullptr;
    QPushButton *m_sendButton = nullptr;
    QPushButton *m_openOutputDirectoryButton = nullptr;
    QTextBrowser *m_chatView = nullptr;
    QPlainTextEdit *m_promptEdit = nullptr;
    QPlainTextEdit *m_diagnosticLog = nullptr;
    QTableWidget *m_tasksTable = nullptr;
    QTableWidget *m_resultsTable = nullptr;
};
