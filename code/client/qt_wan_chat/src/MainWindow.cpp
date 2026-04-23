#include "MainWindow.h"

#include "utils/WslPathUtils.h"

#include <QDateTime>
#include <QDir>
#include <QFileInfo>
#include <QFormLayout>
#include <QHeaderView>
#include <QLabel>
#include <QLineEdit>
#include <QProcess>
#include <QPushButton>
#include <QCoreApplication>
#include <QShortcut>
#include <QSplitter>
#include <QStatusBar>
#include <QTableWidget>
#include <QTableWidgetItem>
#include <QTextBrowser>
#include <QTextCursor>
#include <QTimer>
#include <QVBoxLayout>
#include <QtGlobal>

#include <algorithm>

namespace {

constexpr auto kDefaultServiceUrl = "http://127.0.0.1:8000";
constexpr auto kDefaultSize = "1280*704";
constexpr auto kAlternateSize = "704*1280";
constexpr auto kDefaultDistro = "Ubuntu-24.04";

QString htmlEscapeAndBreaks(QString text)
{
    text = text.toHtmlEscaped();
    text.replace(QStringLiteral("\n"), QStringLiteral("<br/>"));
    return text;
}

bool newerDateTimeFirst(const QDateTime &left, const QString &leftRaw, const QDateTime &right, const QString &rightRaw)
{
    if (left.isValid() && right.isValid()) {
        return left > right;
    }
    if (left.isValid()) {
        return true;
    }
    if (right.isValid()) {
        return false;
    }
    return leftRaw > rightRaw;
}

} // namespace

MainWindow::MainWindow(QWidget *parent)
    : QMainWindow(parent)
{
    setupUi();
    connectSignals();

    QString error;
    if (!m_apiClient.setBaseUrlString(QString::fromLatin1(kDefaultServiceUrl), &error)) {
        appendDiagnostic(error);
    }

    QTimer::singleShot(0, m_promptEdit, [this]() {
        if (m_promptEdit != nullptr) {
            m_promptEdit->setFocus();
        }
    });
    QTimer::singleShot(0, this, &MainWindow::refreshInitialData);
}

void MainWindow::setupUi()
{
    setWindowTitle(QStringLiteral("Wan Chat Client MVP"));
    resize(1600, 920);

    auto *splitter = new QSplitter(Qt::Horizontal, this);
    splitter->addWidget(buildTasksPanel());
    splitter->addWidget(buildChatPanel());
    splitter->addWidget(buildConfigPanel());
    splitter->setStretchFactor(0, 2);
    splitter->setStretchFactor(1, 3);
    splitter->setStretchFactor(2, 3);
    setCentralWidget(splitter);

    statusBar()->showMessage(QStringLiteral("Ready"), 3000);

    m_pollTimer = new QTimer(this);
    m_pollTimer->setInterval(kPollIntervalMs);
    m_smokeTestTimeoutTimer = new QTimer(this);
    m_smokeTestTimeoutTimer->setSingleShot(true);
    connect(
        m_smokeTestTimeoutTimer,
        &QTimer::timeout,
        this,
        [this]() {
            finishSmokeTest(false, QStringLiteral("Smoke test timed out before reaching a terminal task state."));
        });
}

void MainWindow::startSmokeTest(const QString &prompt, int timeoutMs)
{
    if (m_smokeTestEnabled) {
        return;
    }

    m_smokeTestEnabled = true;
    m_smokeTestCompleted = false;
    m_smokeTestTaskId.clear();

    appendDiagnostic(QStringLiteral("Smoke test scheduled."));
    m_smokeTestTimeoutTimer->start(timeoutMs);

    QTimer::singleShot(1200, this, [this, prompt]() {
        m_promptEdit->setPlainText(prompt);
        sendPrompt();
    });
}

QWidget *MainWindow::buildTasksPanel()
{
    auto *panel = new QWidget(this);
    auto *layout = new QVBoxLayout(panel);
    layout->setContentsMargins(8, 8, 8, 8);

    auto *label = new QLabel(QStringLiteral("Tasks"), panel);
    layout->addWidget(label);

    m_tasksTable = new QTableWidget(panel);
    m_tasksTable->setColumnCount(4);
    m_tasksTable->setHorizontalHeaderLabels(
        {QStringLiteral("Status"), QStringLiteral("Task ID"), QStringLiteral("Prompt"), QStringLiteral("Updated")});
    m_tasksTable->setSelectionBehavior(QAbstractItemView::SelectRows);
    m_tasksTable->setSelectionMode(QAbstractItemView::SingleSelection);
    m_tasksTable->setEditTriggers(QAbstractItemView::NoEditTriggers);
    m_tasksTable->setAlternatingRowColors(true);
    m_tasksTable->verticalHeader()->setVisible(false);
    m_tasksTable->horizontalHeader()->setStretchLastSection(true);
    m_tasksTable->horizontalHeader()->setSectionResizeMode(0, QHeaderView::ResizeToContents);
    m_tasksTable->horizontalHeader()->setSectionResizeMode(1, QHeaderView::ResizeToContents);
    m_tasksTable->horizontalHeader()->setSectionResizeMode(2, QHeaderView::Stretch);
    m_tasksTable->horizontalHeader()->setSectionResizeMode(3, QHeaderView::ResizeToContents);
    layout->addWidget(m_tasksTable);

    return panel;
}

QWidget *MainWindow::buildChatPanel()
{
    auto *panel = new QWidget(this);
    auto *layout = new QVBoxLayout(panel);
    layout->setContentsMargins(8, 8, 8, 8);

    auto *label = new QLabel(QStringLiteral("Chat"), panel);
    layout->addWidget(label);

    m_chatView = new QTextBrowser(panel);
    m_chatView->setReadOnly(true);
    layout->addWidget(m_chatView, 1);

    auto *promptLabel = new QLabel(QStringLiteral("Prompt"), panel);
    layout->addWidget(promptLabel);

    m_promptEdit = new QPlainTextEdit(panel);
    m_promptEdit->setPlaceholderText(QStringLiteral("Describe the video you want to generate..."));
    m_promptEdit->setTabChangesFocus(true);
    m_promptEdit->setMaximumBlockCount(200);
    layout->addWidget(m_promptEdit);

    m_sendButton = new QPushButton(QStringLiteral("Send"), panel);
    layout->addWidget(m_sendButton);

    auto *sendShortcut = new QShortcut(QKeySequence(Qt::CTRL | Qt::Key_Return), panel);
    connect(sendShortcut, &QShortcut::activated, this, &MainWindow::sendPrompt);

    return panel;
}

QWidget *MainWindow::buildConfigPanel()
{
    auto *panel = new QWidget(this);
    auto *layout = new QVBoxLayout(panel);
    layout->setContentsMargins(8, 8, 8, 8);

    auto *configLabel = new QLabel(QStringLiteral("Configuration"), panel);
    layout->addWidget(configLabel);

    auto *form = new QFormLayout();

    m_serviceUrlEdit = new QLineEdit(QString::fromLatin1(kDefaultServiceUrl), panel);
    m_serviceUrlEdit->setPlaceholderText(QStringLiteral("http://127.0.0.1:8000"));
    form->addRow(QStringLiteral("Service URL"), m_serviceUrlEdit);

    m_applyServiceUrlButton = new QPushButton(QStringLiteral("Apply URL"), panel);
    form->addRow(QString(), m_applyServiceUrlButton);

    m_sizeCombo = new QComboBox(panel);
    m_sizeCombo->setEditable(true);
    m_sizeCombo->addItems({QString::fromLatin1(kDefaultSize), QString::fromLatin1(kAlternateSize)});
    m_sizeCombo->setCurrentText(QString::fromLatin1(kDefaultSize));
    form->addRow(QStringLiteral("Size"), m_sizeCombo);

    m_wslDistroEdit = new QLineEdit(QString::fromLatin1(kDefaultDistro), panel);
    form->addRow(QStringLiteral("WSL Distro"), m_wslDistroEdit);

    m_outputDirectoryEdit = new QLineEdit(panel);
    m_outputDirectoryEdit->setReadOnly(true);
    m_outputDirectoryEdit->setPlaceholderText(QStringLiteral("Waiting for a succeeded task or selected result"));
    form->addRow(QStringLiteral("Output Directory"), m_outputDirectoryEdit);

    layout->addLayout(form);

    auto *resultsLabel = new QLabel(QStringLiteral("Results"), panel);
    layout->addWidget(resultsLabel);

    m_resultsTable = new QTableWidget(panel);
    m_resultsTable->setColumnCount(4);
    m_resultsTable->setHorizontalHeaderLabels(
        {QStringLiteral("Task ID"), QStringLiteral("Output Path"), QStringLiteral("Exists"), QStringLiteral("Created")});
    m_resultsTable->setSelectionBehavior(QAbstractItemView::SelectRows);
    m_resultsTable->setSelectionMode(QAbstractItemView::SingleSelection);
    m_resultsTable->setEditTriggers(QAbstractItemView::NoEditTriggers);
    m_resultsTable->setAlternatingRowColors(true);
    m_resultsTable->verticalHeader()->setVisible(false);
    m_resultsTable->horizontalHeader()->setStretchLastSection(true);
    m_resultsTable->horizontalHeader()->setSectionResizeMode(0, QHeaderView::ResizeToContents);
    m_resultsTable->horizontalHeader()->setSectionResizeMode(1, QHeaderView::Stretch);
    m_resultsTable->horizontalHeader()->setSectionResizeMode(2, QHeaderView::ResizeToContents);
    m_resultsTable->horizontalHeader()->setSectionResizeMode(3, QHeaderView::ResizeToContents);
    layout->addWidget(m_resultsTable, 1);

    m_openOutputDirectoryButton = new QPushButton(QStringLiteral("Open Output Directory"), panel);
    layout->addWidget(m_openOutputDirectoryButton);

    auto *diagnosticLabel = new QLabel(QStringLiteral("Diagnostics"), panel);
    layout->addWidget(diagnosticLabel);

    m_diagnosticLog = new QPlainTextEdit(panel);
    m_diagnosticLog->setReadOnly(true);
    m_diagnosticLog->setMaximumBlockCount(400);
    m_diagnosticLog->setMinimumHeight(180);
    layout->addWidget(m_diagnosticLog);

    return panel;
}

void MainWindow::connectSignals()
{
    connect(m_applyServiceUrlButton, &QPushButton::clicked, this, &MainWindow::applyServiceUrl);
    connect(m_serviceUrlEdit, &QLineEdit::returnPressed, this, &MainWindow::applyServiceUrl);
    connect(m_sendButton, &QPushButton::clicked, this, &MainWindow::sendPrompt);
    connect(m_pollTimer, &QTimer::timeout, this, &MainWindow::pollActiveTasks);
    connect(m_tasksTable, &QTableWidget::itemSelectionChanged, this, &MainWindow::updateOutputDirectoryField);
    connect(m_resultsTable, &QTableWidget::itemSelectionChanged, this, &MainWindow::updateOutputDirectoryField);
    connect(m_wslDistroEdit, &QLineEdit::textChanged, this, &MainWindow::updateOutputDirectoryField);
    connect(m_openOutputDirectoryButton, &QPushButton::clicked, this, &MainWindow::openSelectedOutputDirectory);

    connect(&m_apiClient, &ApiClient::healthChecked, this, &MainWindow::onHealthChecked);
    connect(&m_apiClient, &ApiClient::taskCreated, this, &MainWindow::onTaskCreated);
    connect(&m_apiClient, &ApiClient::taskFetched, this, &MainWindow::onTaskFetched);
    connect(&m_apiClient, &ApiClient::tasksFetched, this, &MainWindow::onTasksFetched);
    connect(&m_apiClient, &ApiClient::resultsFetched, this, &MainWindow::onResultsFetched);
    connect(&m_apiClient, &ApiClient::requestFailed, this, &MainWindow::onRequestFailed);
}

void MainWindow::applyServiceUrl()
{
    QString error;
    if (!m_apiClient.setBaseUrlString(m_serviceUrlEdit->text(), &error)) {
        appendDiagnostic(error);
        appendChatMessage(QStringLiteral("System"), error);
        showUserNotice(QStringLiteral("Invalid service URL."));
        return;
    }

    const QString appliedUrl = m_apiClient.baseUrl().toString();
    appendDiagnostic(QStringLiteral("Service URL applied: %1").arg(appliedUrl));
    appendChatMessage(QStringLiteral("System"), QStringLiteral("Service URL updated to %1").arg(appliedUrl));
    showUserNotice(QStringLiteral("Service URL updated."));
    refreshInitialData();
}

void MainWindow::sendPrompt()
{
    const QString prompt = m_promptEdit->toPlainText().trimmed();
    if (prompt.isEmpty()) {
        const QString message = QStringLiteral("Prompt must not be empty.");
        appendDiagnostic(message);
        appendChatMessage(QStringLiteral("System"), message);
        showUserNotice(message);
        return;
    }

    const QString size = m_sizeCombo->currentText().trimmed();
    if (size != QString::fromLatin1(kDefaultSize) && size != QString::fromLatin1(kAlternateSize)) {
        const QString message = QStringLiteral("Size must be 1280*704 or 704*1280.");
        appendDiagnostic(message);
        appendChatMessage(QStringLiteral("System"), message);
        showUserNotice(message);
        return;
    }

    appendChatMessage(QStringLiteral("User"), prompt);
    showUserNotice(QStringLiteral("Creating task..."));
    appendDiagnostic(QStringLiteral("Submitting task with size=%1 to %2")
                         .arg(size, m_apiClient.baseUrl().toString()));
    m_apiClient.createTask(prompt, size);
    m_promptEdit->clear();
}

void MainWindow::refreshInitialData()
{
    m_apiClient.checkHealth();
    m_apiClient.fetchTasks(kListLimit);
    m_apiClient.fetchResults(kListLimit);
}

void MainWindow::pollActiveTasks()
{
    const auto taskIds = m_activeTaskIds.values();
    for (const QString &taskId : taskIds) {
        if (m_inFlightTaskIds.contains(taskId)) {
            continue;
        }
        m_inFlightTaskIds.insert(taskId);
        m_apiClient.fetchTask(taskId);
    }
}

void MainWindow::updateOutputDirectoryField()
{
    QString error;
    const QString directory = currentSelectedOutputDirectory(&error);
    if (!directory.isEmpty()) {
        m_outputDirectoryEdit->setText(directory);
        return;
    }

    m_outputDirectoryEdit->clear();
    if (!error.isEmpty()) {
        appendDiagnostic(QStringLiteral("Output directory preview unavailable: %1").arg(error));
    }
}

void MainWindow::openSelectedOutputDirectory()
{
    QString error;
    const QString directory = currentSelectedOutputDirectory(&error);
    if (directory.isEmpty()) {
        const QString message = error.isEmpty()
            ? QStringLiteral("There is no output path available to open.")
            : error;
        appendDiagnostic(message);
        appendChatMessage(QStringLiteral("System"), message);
        showUserNotice(message);
        return;
    }

    if (!QDir(directory).exists()) {
        const QString message = QStringLiteral("Output directory does not exist: %1").arg(directory);
        appendDiagnostic(message);
        appendChatMessage(QStringLiteral("System"), message);
        showUserNotice(message);
        return;
    }

    if (!QProcess::startDetached(QStringLiteral("explorer.exe"), {directory})) {
        const QString message = QStringLiteral("Failed to open output directory with explorer.exe: %1").arg(directory);
        appendDiagnostic(message);
        appendChatMessage(QStringLiteral("System"), message);
        showUserNotice(message);
        return;
    }

    appendDiagnostic(QStringLiteral("Opened output directory: %1").arg(directory));
    showUserNotice(QStringLiteral("Opened output directory."));
}

void MainWindow::onHealthChecked(const TaskModels::HealthResponse &health)
{
    const QString message = QStringLiteral("Connected to service '%1' at %2")
                                .arg(health.service, m_apiClient.baseUrl().toString());
    appendDiagnostic(message);
    showUserNotice(QStringLiteral("Health check passed."));
}

void MainWindow::onTaskCreated(const TaskModels::TaskSummary &task)
{
    syncTaskSummary(task);
    m_activeTaskIds.insert(task.taskId);
    startPollingIfNeeded();

    if (m_smokeTestEnabled && m_smokeTestTaskId.isEmpty()) {
        m_smokeTestTaskId = task.taskId;
    }

    appendChatMessage(
        QStringLiteral("System"),
        QStringLiteral("Task created\n"
                       "task_id: %1\n"
                       "status: %2\n"
                       "log_path: %3")
            .arg(task.taskId, task.status, task.logPath));
    appendDiagnostic(QStringLiteral("Task created: %1 status=%2").arg(task.taskId, task.status));
    refreshTasksTable();
    showUserNotice(QStringLiteral("Task created: %1").arg(task.taskId));
}

void MainWindow::onTaskFetched(const TaskModels::TaskDetail &task)
{
    m_inFlightTaskIds.remove(task.taskId);

    const TaskModels::TaskDetail previous = m_tasks.value(task.taskId);
    const bool hadPrevious = m_tasks.contains(task.taskId);
    syncTaskDetail(task);
    refreshTasksTable();

    if (!hadPrevious || previous.status != task.status || previous.outputPath != task.outputPath
        || previous.errorMessage != task.errorMessage) {
        QString message = QStringLiteral("Task %1 -> %2").arg(task.taskId, task.status);
        if (!task.outputPath.isEmpty()) {
            message += QStringLiteral("\noutput_path: %1").arg(task.outputPath);
        }
        if (!task.errorMessage.isEmpty()) {
            message += QStringLiteral("\nerror_message: %1").arg(task.errorMessage);
        }
        appendChatMessage(QStringLiteral("System"), message);
        appendDiagnostic(QStringLiteral("Task update: %1").arg(message.simplified()));
    }

    if (isTerminalStatus(task.status)) {
        m_activeTaskIds.remove(task.taskId);
        m_inFlightTaskIds.remove(task.taskId);
        stopPollingIfIdle();
        m_apiClient.fetchResults(kListLimit);
        if (task.status == QStringLiteral("failed")) {
            showUserNotice(QStringLiteral("Task failed: %1").arg(task.taskId));
        } else if (task.status == QStringLiteral("succeeded")) {
            showUserNotice(QStringLiteral("Task succeeded: %1").arg(task.taskId));
        }

        if (m_smokeTestEnabled && task.taskId == m_smokeTestTaskId) {
            QString summary = QStringLiteral("Smoke test reached terminal state: %1").arg(task.status);
            if (!task.outputPath.isEmpty()) {
                summary += QStringLiteral(" | output_path=%1").arg(task.outputPath);
            }
            if (!task.errorMessage.isEmpty()) {
                summary += QStringLiteral(" | error_message=%1").arg(task.errorMessage);
            }
            finishSmokeTest(true, summary);
        }
    } else {
        startPollingIfNeeded();
    }
}

void MainWindow::onTasksFetched(const TaskModels::TaskListResponse &tasks)
{
    for (const TaskModels::TaskSummary &task : tasks.items) {
        syncTaskSummary(task);
        if (isTerminalStatus(task.status)) {
            m_activeTaskIds.remove(task.taskId);
            m_inFlightTaskIds.remove(task.taskId);
        } else {
            m_activeTaskIds.insert(task.taskId);
        }
    }

    refreshTasksTable();
    startPollingIfNeeded();
    appendDiagnostic(QStringLiteral("Loaded %1 task item(s).").arg(tasks.items.size()));
}

void MainWindow::onResultsFetched(const TaskModels::ResultListResponse &results)
{
    m_results.clear();
    for (const TaskModels::ResultItem &result : results.items) {
        syncResultItem(result);
    }

    refreshResultsTable();
    appendDiagnostic(QStringLiteral("Loaded %1 result item(s).").arg(results.items.size()));
}

void MainWindow::onRequestFailed(const RequestFailure &failure)
{
    if (failure.kind == RequestKind::FetchTask) {
        const QString taskId = failure.url.path().section(QLatin1Char('/'), -1);
        if (!taskId.isEmpty()) {
            m_inFlightTaskIds.remove(taskId);
        }
    }

    QString message = failure.userMessage;
    if (message.isEmpty()) {
        message = QStringLiteral("%1 failed.").arg(requestKindName(failure.kind));
    }
    if (failure.httpStatus > 0) {
        message += QStringLiteral(" [HTTP %1]").arg(failure.httpStatus);
    }
    if (!failure.stableCode.isEmpty()) {
        message += QStringLiteral(" [code=%1]").arg(failure.stableCode);
    }

    QString diagnostic = QStringLiteral("%1 | url=%2")
                             .arg(message, failure.url.toString());
    if (!failure.details.isEmpty()) {
        diagnostic += QStringLiteral(" | details=%1").arg(failure.details);
    }

    appendDiagnostic(diagnostic);
    appendChatMessage(QStringLiteral("System"), message);
    showUserNotice(message);

    if (!m_smokeTestEnabled || m_smokeTestCompleted) {
        return;
    }

    const bool createFailure = m_smokeTestTaskId.isEmpty() && failure.kind == RequestKind::CreateTask;
    const bool pollFailure = !m_smokeTestTaskId.isEmpty() && failure.kind == RequestKind::FetchTask;
    if (createFailure || pollFailure) {
        finishSmokeTest(false, message);
    }
}

void MainWindow::appendChatMessage(const QString &role, const QString &message)
{
    const QString stamp = QDateTime::currentDateTime().toString(QStringLiteral("yyyy-MM-dd HH:mm:ss"));
    const QString html = QStringLiteral("<p><b>[%1] %2</b><br/>%3</p>")
                             .arg(stamp, htmlEscapeAndBreaks(role), htmlEscapeAndBreaks(message));
    m_chatView->append(html);
    m_chatView->moveCursor(QTextCursor::End);
}

void MainWindow::appendDiagnostic(const QString &message)
{
    const QString line = QStringLiteral("[%1] %2")
                             .arg(QDateTime::currentDateTime().toString(Qt::ISODate), message);
    m_diagnosticLog->appendPlainText(line);
    qWarning().noquote() << line;
}

void MainWindow::showUserNotice(const QString &message, int timeoutMs)
{
    statusBar()->showMessage(message, timeoutMs);
}

void MainWindow::finishSmokeTest(bool success, const QString &summary)
{
    if (m_smokeTestCompleted) {
        return;
    }

    m_smokeTestCompleted = true;
    if (m_smokeTestTimeoutTimer->isActive()) {
        m_smokeTestTimeoutTimer->stop();
    }
    appendDiagnostic(summary);
    emit smokeTestFinished(success, summary);
}

void MainWindow::refreshTasksTable()
{
    const QString preservedTaskId = selectedTaskId();
    QList<TaskModels::TaskDetail> tasks = m_tasks.values();

    std::sort(tasks.begin(), tasks.end(), [](const TaskModels::TaskDetail &left, const TaskModels::TaskDetail &right) {
        return newerDateTimeFirst(left.updateTime, left.updateTimeRaw, right.updateTime, right.updateTimeRaw);
    });

    m_tasksTable->setRowCount(tasks.size());
    for (int row = 0; row < tasks.size(); ++row) {
        const TaskModels::TaskDetail &task = tasks.at(row);

        auto *statusItem = new QTableWidgetItem(task.status);
        statusItem->setData(Qt::UserRole, task.taskId);
        auto *taskIdItem = new QTableWidgetItem(task.taskId);
        auto *promptItem = new QTableWidgetItem(task.prompt);
        promptItem->setToolTip(task.prompt);
        auto *updatedItem = new QTableWidgetItem(formatTimestamp(task.updateTime, task.updateTimeRaw));

        m_tasksTable->setItem(row, 0, statusItem);
        m_tasksTable->setItem(row, 1, taskIdItem);
        m_tasksTable->setItem(row, 2, promptItem);
        m_tasksTable->setItem(row, 3, updatedItem);
    }

    if (!preservedTaskId.isEmpty()) {
        for (int row = 0; row < m_tasksTable->rowCount(); ++row) {
            QTableWidgetItem *item = m_tasksTable->item(row, 0);
            if (item != nullptr && item->data(Qt::UserRole).toString() == preservedTaskId) {
                m_tasksTable->selectRow(row);
                break;
            }
        }
    }
}

void MainWindow::refreshResultsTable()
{
    const QString preservedTaskId = selectedResultTaskId();
    QList<TaskModels::ResultItem> results = m_results.values();

    std::sort(results.begin(), results.end(), [](const TaskModels::ResultItem &left, const TaskModels::ResultItem &right) {
        return newerDateTimeFirst(left.createTime, left.createTimeRaw, right.createTime, right.createTimeRaw);
    });

    m_resultsTable->setRowCount(results.size());
    for (int row = 0; row < results.size(); ++row) {
        const TaskModels::ResultItem &result = results.at(row);

        auto *taskIdItem = new QTableWidgetItem(result.taskId);
        taskIdItem->setData(Qt::UserRole, result.taskId);
        auto *pathItem = new QTableWidgetItem(result.outputPath);
        pathItem->setToolTip(result.outputPath);
        auto *existsItem = new QTableWidgetItem(result.outputExists ? QStringLiteral("true") : QStringLiteral("false"));
        auto *createdItem = new QTableWidgetItem(formatTimestamp(result.createTime, result.createTimeRaw));

        m_resultsTable->setItem(row, 0, taskIdItem);
        m_resultsTable->setItem(row, 1, pathItem);
        m_resultsTable->setItem(row, 2, existsItem);
        m_resultsTable->setItem(row, 3, createdItem);
    }

    if (!preservedTaskId.isEmpty()) {
        for (int row = 0; row < m_resultsTable->rowCount(); ++row) {
            QTableWidgetItem *item = m_resultsTable->item(row, 0);
            if (item != nullptr && item->data(Qt::UserRole).toString() == preservedTaskId) {
                m_resultsTable->selectRow(row);
                break;
            }
        }
    }
}

void MainWindow::syncTaskSummary(const TaskModels::TaskSummary &task)
{
    syncTaskDetail(summaryToDetail(task));
}

void MainWindow::syncTaskDetail(const TaskModels::TaskDetail &task)
{
    m_tasks.insert(task.taskId, task);
    updateOutputDirectoryField();
}

void MainWindow::syncResultItem(const TaskModels::ResultItem &result)
{
    m_results.insert(result.taskId, result);
    updateOutputDirectoryField();
}

QString MainWindow::selectedTaskId() const
{
    const QModelIndexList rows = m_tasksTable->selectionModel() != nullptr
        ? m_tasksTable->selectionModel()->selectedRows()
        : QModelIndexList{};
    if (rows.isEmpty()) {
        return {};
    }
    QTableWidgetItem *item = m_tasksTable->item(rows.first().row(), 0);
    return item != nullptr ? item->data(Qt::UserRole).toString() : QString{};
}

QString MainWindow::selectedResultTaskId() const
{
    const QModelIndexList rows = m_resultsTable->selectionModel() != nullptr
        ? m_resultsTable->selectionModel()->selectedRows()
        : QModelIndexList{};
    if (rows.isEmpty()) {
        return {};
    }
    QTableWidgetItem *item = m_resultsTable->item(rows.first().row(), 0);
    return item != nullptr ? item->data(Qt::UserRole).toString() : QString{};
}

QString MainWindow::currentSelectedOutputPath() const
{
    const QString resultTaskId = selectedResultTaskId();
    if (!resultTaskId.isEmpty() && m_results.contains(resultTaskId)) {
        return m_results.value(resultTaskId).outputPath;
    }

    const QString taskId = selectedTaskId();
    if (!taskId.isEmpty() && m_tasks.contains(taskId)) {
        return m_tasks.value(taskId).outputPath;
    }

    return {};
}

QString MainWindow::currentSelectedOutputDirectory(QString *error) const
{
    if (error != nullptr) {
        error->clear();
    }

    const QString outputPath = currentSelectedOutputPath();
    if (outputPath.trimmed().isEmpty()) {
        return {};
    }

    QString directoryPath;
    QString conversionError;
    if (!WslPathUtils::outputDirectoryForLinuxFile(outputPath, m_wslDistroEdit->text(), directoryPath, conversionError)) {
        if (error != nullptr) {
            *error = conversionError;
        }
        return {};
    }

    return directoryPath;
}

bool MainWindow::isTerminalStatus(const QString &status) const
{
    return status == QStringLiteral("succeeded") || status == QStringLiteral("failed");
}

void MainWindow::startPollingIfNeeded()
{
    if (!m_activeTaskIds.isEmpty() && !m_pollTimer->isActive()) {
        m_pollTimer->start();
    }
}

void MainWindow::stopPollingIfIdle()
{
    if (m_activeTaskIds.isEmpty()) {
        m_pollTimer->stop();
    }
}

TaskModels::TaskDetail MainWindow::summaryToDetail(const TaskModels::TaskSummary &task) const
{
    TaskModels::TaskDetail detail;
    detail.taskId = task.taskId;
    detail.status = task.status;
    detail.prompt = task.prompt;
    detail.outputPath = task.outputPath;
    detail.errorMessage = task.errorMessage;
    detail.logPath = task.logPath;
    detail.createTimeRaw = task.createTimeRaw;
    detail.updateTimeRaw = task.updateTimeRaw;
    detail.createTime = task.createTime;
    detail.updateTime = task.updateTime;
    detail.outputExists = false;
    return detail;
}

QString MainWindow::formatTimestamp(const QDateTime &dateTime, const QString &fallback) const
{
    if (dateTime.isValid()) {
        return dateTime.toLocalTime().toString(QStringLiteral("yyyy-MM-dd HH:mm:ss"));
    }
    return fallback;
}
