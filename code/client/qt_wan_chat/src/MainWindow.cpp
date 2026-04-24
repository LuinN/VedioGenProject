#include "MainWindow.h"

#include "utils/WslPathUtils.h"

#include <QDateTime>
#include <QDesktopServices>
#include <QDialog>
#include <QDir>
#include <QDirIterator>
#include <QEvent>
#include <QFile>
#include <QFileDialog>
#include <QFileInfo>
#include <QFormLayout>
#include <QFrame>
#include <QHeaderView>
#include <QHBoxLayout>
#include <QImageReader>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QJsonParseError>
#include <QKeySequence>
#include <QLabel>
#include <QLineEdit>
#include <QListWidget>
#include <QListWidgetItem>
#include <QMediaPlayer>
#include <QMessageBox>
#include <QPixmap>
#include <QProgressBar>
#include <QProcess>
#include <QPushButton>
#include <QCoreApplication>
#include <QSaveFile>
#include <QShortcut>
#include <QSettings>
#include <QSplitter>
#include <QStandardPaths>
#include <QStatusBar>
#include <QStringList>
#include <QTableWidget>
#include <QTableWidgetItem>
#include <QTextBrowser>
#include <QTextCursor>
#include <QTimer>
#include <QUuid>
#include <QVideoFrame>
#include <QVideoSink>
#include <QVBoxLayout>
#include <QtGlobal>

#include <algorithm>
#include <utility>

namespace {

constexpr auto kDefaultServiceUrl = "http://127.0.0.1:8000";
constexpr auto kDefaultSize = "1280*704";
constexpr auto kAlternateSize = "704*1280";
constexpr auto kDefaultDistro = "Ubuntu-24.04";
constexpr auto kDownloadDirectorySetting = "downloads/directory";
constexpr auto kVideoIndexFileName = "downloaded_videos.json";
constexpr auto kDeletedTasksFileName = "deleted_tasks.json";
constexpr auto kTaskMetadataFileName = "metadata.json";
constexpr auto kPreviewVideoFileName = "result.mp4";
constexpr auto kThumbnailFileName = "thumbnail.png";
constexpr auto kThumbnailVersionFileName = "thumbnail.version";
constexpr auto kThumbnailVersion = "2";
constexpr auto kDownloadPurposeUser = "user";
constexpr auto kDownloadPurposePreview = "preview";
constexpr qint64 kMaxInputImageBytes = 20ll * 1024ll * 1024ll;

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

QString formatProgressText(const TaskModels::TaskDetail &task)
{
    if (task.progressPercent >= 0) {
        if (task.progressCurrent >= 0 && task.progressTotal > 0) {
            return QStringLiteral("%1% (%2/%3)")
                .arg(task.progressPercent)
                .arg(task.progressCurrent)
                .arg(task.progressTotal);
        }
        return QStringLiteral("%1%").arg(task.progressPercent);
    }
    if (task.progressCurrent >= 0 && task.progressTotal > 0) {
        return QStringLiteral("%1/%2").arg(task.progressCurrent).arg(task.progressTotal);
    }
    return QStringLiteral("-");
}

QString formatStageText(const TaskModels::TaskDetail &task)
{
    if (!task.statusMessage.trimmed().isEmpty()) {
        return task.statusMessage.trimmed();
    }
    return QStringLiteral("-");
}

QString formatRuntimeSummary(const TaskModels::TaskDetail &task)
{
    QStringList parts;
    parts << task.status;
    const QString stage = formatStageText(task);
    if (stage != QStringLiteral("-")) {
        parts << stage;
    }
    const QString progress = formatProgressText(task);
    if (progress != QStringLiteral("-")) {
        parts << progress;
    }
    return parts.join(QStringLiteral(" | "));
}

bool visibleTaskStateChanged(const TaskModels::TaskDetail &previous, const TaskModels::TaskDetail &task)
{
    return previous.status != task.status
        || previous.statusMessage != task.statusMessage
        || previous.progressCurrent != task.progressCurrent
        || previous.progressTotal != task.progressTotal
        || previous.progressPercent != task.progressPercent
        || previous.outputPath != task.outputPath
        || previous.errorMessage != task.errorMessage;
}

QString formatTaskUpdateMessage(const TaskModels::TaskDetail &task)
{
    QString message = QStringLiteral("Task %1 -> %2").arg(task.taskId, formatRuntimeSummary(task));
    if (!task.outputPath.isEmpty()) {
        message += QStringLiteral("\noutput_path: %1").arg(task.outputPath);
    }
    if (!task.errorMessage.isEmpty()) {
        message += QStringLiteral("\nerror_message: %1").arg(task.errorMessage);
    }
    return message;
}

bool isWslSharePath(const QString &path)
{
    return path.startsWith(QStringLiteral("\\\\wsl$\\"), Qt::CaseInsensitive)
        || path.startsWith(QStringLiteral("\\\\wsl.localhost\\"), Qt::CaseInsensitive);
}

QString formatFileSize(qint64 bytes)
{
    if (bytes < 0) {
        return QStringLiteral("-");
    }
    if (bytes < 1024) {
        return QStringLiteral("%1 B").arg(bytes);
    }
    const double kib = static_cast<double>(bytes) / 1024.0;
    if (kib < 1024.0) {
        return QStringLiteral("%1 KiB").arg(kib, 0, 'f', 1);
    }
    const double mib = kib / 1024.0;
    if (mib < 1024.0) {
        return QStringLiteral("%1 MiB").arg(mib, 0, 'f', 1);
    }
    return QStringLiteral("%1 GiB").arg(mib / 1024.0, 0, 'f', 2);
}

QString taskVideoFileName(const QString &taskId)
{
    return QStringLiteral("%1.mp4").arg(taskId.trimmed());
}

QString normalizedTaskMode(const TaskModels::TaskSummary &task)
{
    QString mode = task.mode.trimmed().toLower();
    if (mode.isEmpty()) {
        mode = task.inputImagePath.trimmed().isEmpty() ? QStringLiteral("t2v") : QStringLiteral("i2v");
    }
    return mode;
}

QString imageFileNameForExtension(const QString &extension)
{
    return QStringLiteral("input_image.%1").arg(extension.toLower());
}

QString cleanUuid()
{
    QString value = QUuid::createUuid().toString(QUuid::WithoutBraces);
    value.replace(QLatin1Char('{'), QLatin1Char('_'));
    value.replace(QLatin1Char('}'), QLatin1Char('_'));
    return value;
}

QString normalizedAbsolutePath(const QString &path)
{
    return QDir::cleanPath(QFileInfo(path).absoluteFilePath());
}

bool pathIsAtOrUnderDirectory(const QString &path, const QString &directory)
{
    const QString normalizedPath = normalizedAbsolutePath(path);
    QString normalizedDirectory = normalizedAbsolutePath(directory);
    if (normalizedPath.compare(normalizedDirectory, Qt::CaseInsensitive) == 0) {
        return true;
    }
    if (!normalizedDirectory.endsWith(QLatin1Char('/'))) {
        normalizedDirectory.append(QLatin1Char('/'));
    }
    return normalizedPath.startsWith(normalizedDirectory, Qt::CaseInsensitive);
}

} // namespace

MainWindow::MainWindow(QWidget *parent)
    : QMainWindow(parent)
{
    setupUi();
    loadPersistentState();
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
    splitter->setStretchFactor(0, 2);
    splitter->setStretchFactor(1, 5);
    splitter->setHandleWidth(1);
    setCentralWidget(splitter);
    setupHiddenResultsTable();
    setupDialogs();
    applyVisualStyle();

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
            finishSmokeTest(false, smokeTaskSnapshotSummary());
        });
}

void MainWindow::startSmokeTest(const QString &prompt, int timeoutMs, const QString &downloadDirectory, const QString &imagePath)
{
    if (m_smokeTestEnabled) {
        return;
    }

    m_smokeTestEnabled = true;
    m_smokeTestCompleted = false;
    m_smokeRequiresDownload = !downloadDirectory.trimmed().isEmpty();
    m_smokeImagePath = imagePath.trimmed();
    m_smokeTestTaskId.clear();

    if (m_smokeRequiresDownload) {
        QString error;
        if (!setDownloadDirectory(downloadDirectory, &error)) {
            finishSmokeTest(false, error);
            return;
        }
    }

    appendDiagnostic(m_smokeImagePath.isEmpty()
                         ? QStringLiteral("Smoke test scheduled.")
                         : QStringLiteral("Smoke i2v test scheduled with image: %1").arg(m_smokeImagePath));
    m_smokeTestTimeoutTimer->start(timeoutMs);

    QTimer::singleShot(1200, this, [this, prompt]() {
        if (!m_smokeImagePath.isEmpty()) {
            QString error;
            if (!setCurrentInputImage(m_smokeImagePath, &error)) {
                finishSmokeTest(false, error);
                return;
            }
        }
        m_promptEdit->setPlainText(prompt);
        sendPrompt();
    });
}

void MainWindow::startTaskMonitorSmoke(const QString &taskId, int timeoutMs, const QString &downloadDirectory)
{
    if (m_smokeTestEnabled) {
        return;
    }

    const QString trimmedTaskId = taskId.trimmed();
    if (trimmedTaskId.isEmpty()) {
        finishSmokeTest(false, QStringLiteral("Smoke task id must not be empty."));
        return;
    }

    m_smokeTestEnabled = true;
    m_smokeTestCompleted = false;
    m_smokeRequiresDownload = !downloadDirectory.trimmed().isEmpty();
    m_smokeImagePath.clear();
    m_smokeTestTaskId = trimmedTaskId;
    m_activeTaskIds.insert(trimmedTaskId);

    if (m_smokeRequiresDownload) {
        QString error;
        if (!setDownloadDirectory(downloadDirectory, &error)) {
            finishSmokeTest(false, error);
            return;
        }
    }

    appendDiagnostic(QStringLiteral("Smoke task monitor scheduled: %1").arg(trimmedTaskId));
    m_smokeTestTimeoutTimer->start(timeoutMs);

    if (!m_inFlightTaskIds.contains(trimmedTaskId)) {
        m_inFlightTaskIds.insert(trimmedTaskId);
        m_apiClient.fetchTask(trimmedTaskId);
    }
    startPollingIfNeeded();
}

QWidget *MainWindow::buildTasksPanel()
{
    auto *panel = new QWidget(this);
    panel->setObjectName(QStringLiteral("sidePanel"));
    auto *layout = new QVBoxLayout(panel);
    layout->setContentsMargins(14, 14, 10, 14);
    layout->setSpacing(10);

    auto *header = new QHBoxLayout();
    header->setContentsMargins(0, 0, 0, 0);
    header->setSpacing(8);

    auto *label = new QLabel(QStringLiteral("Tasks"), panel);
    label->setProperty("role", QStringLiteral("sectionTitle"));
    header->addWidget(label);
    header->addStretch(1);

    m_deleteTaskButton = new QPushButton(QStringLiteral("Delete"), panel);
    m_deleteTaskButton->setObjectName(QStringLiteral("toolbarButton"));
    m_deleteTaskButton->setToolTip(QStringLiteral("Delete selected task data. Downloaded videos are kept."));
    m_deleteTaskButton->setEnabled(false);
    header->addWidget(m_deleteTaskButton);

    layout->addLayout(header);

    m_tasksList = new QListWidget(panel);
    m_tasksList->setSelectionMode(QAbstractItemView::SingleSelection);
    m_tasksList->setSpacing(8);
    m_tasksList->setUniformItemSizes(false);
    m_tasksList->setHorizontalScrollBarPolicy(Qt::ScrollBarAlwaysOff);
    layout->addWidget(m_tasksList);

    return panel;
}

QWidget *MainWindow::buildChatPanel()
{
    auto *panel = new QWidget(this);
    panel->setObjectName(QStringLiteral("chatPanel"));
    auto *layout = new QVBoxLayout(panel);
    layout->setContentsMargins(16, 14, 16, 14);
    layout->setSpacing(12);

    auto *toolbar = new QHBoxLayout();
    toolbar->setContentsMargins(0, 0, 0, 0);
    toolbar->setSpacing(8);

    auto *label = new QLabel(QStringLiteral("Wan Chat"), panel);
    label->setProperty("role", QStringLiteral("sectionTitle"));
    toolbar->addWidget(label);
    toolbar->addStretch(1);

    m_configurationButton = new QPushButton(QStringLiteral("Configuration"), panel);
    m_configurationButton->setObjectName(QStringLiteral("toolbarButton"));
    toolbar->addWidget(m_configurationButton);

    m_videosButton = new QPushButton(QStringLiteral("Videos"), panel);
    m_videosButton->setObjectName(QStringLiteral("toolbarButton"));
    toolbar->addWidget(m_videosButton);

    m_diagnosticsButton = new QPushButton(QStringLiteral("Diagnostics"), panel);
    m_diagnosticsButton->setObjectName(QStringLiteral("toolbarButton"));
    toolbar->addWidget(m_diagnosticsButton);

    layout->addLayout(toolbar);

    m_chatView = new QTextBrowser(panel);
    m_chatView->setObjectName(QStringLiteral("chatView"));
    m_chatView->setReadOnly(true);
    layout->addWidget(m_chatView, 1);

    auto *composerFrame = new QFrame(panel);
    composerFrame->setObjectName(QStringLiteral("composerFrame"));
    auto *composerLayout = new QVBoxLayout(composerFrame);
    composerLayout->setContentsMargins(10, 8, 10, 8);
    composerLayout->setSpacing(6);

    m_inputImagePreview = new QFrame(composerFrame);
    m_inputImagePreview->setObjectName(QStringLiteral("inputImagePreview"));
    m_inputImagePreview->setVisible(false);
    auto *previewLayout = new QHBoxLayout(m_inputImagePreview);
    previewLayout->setContentsMargins(8, 8, 8, 8);
    previewLayout->setSpacing(8);

    m_inputImageThumbnail = new QLabel(m_inputImagePreview);
    m_inputImageThumbnail->setFixedSize(96, 64);
    m_inputImageThumbnail->setAlignment(Qt::AlignCenter);
    m_inputImageThumbnail->setFrameShape(QFrame::StyledPanel);
    m_inputImageThumbnail->setScaledContents(false);
    previewLayout->addWidget(m_inputImageThumbnail);

    m_inputImageNameLabel = new QLabel(m_inputImagePreview);
    m_inputImageNameLabel->setTextInteractionFlags(Qt::TextSelectableByMouse);
    m_inputImageNameLabel->setWordWrap(true);
    previewLayout->addWidget(m_inputImageNameLabel, 1);

    m_removeImageButton = new QPushButton(QStringLiteral("Remove"), m_inputImagePreview);
    previewLayout->addWidget(m_removeImageButton);

    composerLayout->addWidget(m_inputImagePreview);

    m_promptEdit = new QPlainTextEdit(composerFrame);
    m_promptEdit->setObjectName(QStringLiteral("promptEdit"));
    m_promptEdit->setPlaceholderText(QStringLiteral("Message Wan..."));
    m_promptEdit->setTabChangesFocus(true);
    m_promptEdit->setMaximumBlockCount(200);
    m_promptEdit->setMinimumHeight(104);
    composerLayout->addWidget(m_promptEdit);

    auto *sendRow = new QHBoxLayout();
    sendRow->setContentsMargins(0, 0, 0, 0);
    m_addImageButton = new QPushButton(QStringLiteral("+"), composerFrame);
    m_addImageButton->setObjectName(QStringLiteral("iconButton"));
    m_addImageButton->setToolTip(QStringLiteral("Add image"));
    m_addImageButton->setFixedWidth(40);
    sendRow->addWidget(m_addImageButton);
    sendRow->addStretch(1);
    m_sendButton = new QPushButton(QStringLiteral("Send"), composerFrame);
    m_sendButton->setObjectName(QStringLiteral("sendButton"));
    sendRow->addWidget(m_sendButton);
    composerLayout->addLayout(sendRow);
    layout->addWidget(composerFrame);

    auto *sendShortcut = new QShortcut(QKeySequence(Qt::CTRL | Qt::Key_Return), panel);
    connect(sendShortcut, &QShortcut::activated, this, &MainWindow::sendPrompt);

    return panel;
}

QWidget *MainWindow::buildConfigPanel()
{
    auto *panel = new QWidget(this);
    panel->setObjectName(QStringLiteral("sidePanel"));
    auto *layout = new QVBoxLayout(panel);
    layout->setContentsMargins(10, 14, 14, 14);
    layout->setSpacing(10);

    auto *configLabel = new QLabel(QStringLiteral("Configuration"), panel);
    configLabel->setProperty("role", QStringLiteral("sectionTitle"));
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

    auto *downloadDirectoryLayout = new QHBoxLayout();
    downloadDirectoryLayout->setContentsMargins(0, 0, 0, 0);
    m_downloadDirectoryEdit = new QLineEdit(panel);
    m_downloadDirectoryEdit->setReadOnly(true);
    m_downloadDirectoryEdit->setPlaceholderText(QStringLiteral("Choose a Windows folder for downloaded videos"));
    m_chooseDownloadDirectoryButton = new QPushButton(QStringLiteral("Choose"), panel);
    downloadDirectoryLayout->addWidget(m_downloadDirectoryEdit, 1);
    downloadDirectoryLayout->addWidget(m_chooseDownloadDirectoryButton);
    form->addRow(QStringLiteral("Download Directory"), downloadDirectoryLayout);

    m_outputDirectoryEdit = new QLineEdit(panel);
    m_outputDirectoryEdit->setReadOnly(true);
    m_outputDirectoryEdit->setPlaceholderText(QStringLiteral("Waiting for a succeeded task or selected result"));
    form->addRow(QStringLiteral("Output Directory"), m_outputDirectoryEdit);

    layout->addLayout(form);

    m_openOutputDirectoryButton = new QPushButton(QStringLiteral("Open Output Directory"), panel);
    layout->addWidget(m_openOutputDirectoryButton);
    layout->addStretch(1);

    return panel;
}

QWidget *MainWindow::buildVideosPanel()
{
    auto *panel = new QWidget(this);
    panel->setObjectName(QStringLiteral("dialogPanel"));
    auto *layout = new QVBoxLayout(panel);
    layout->setContentsMargins(14, 14, 14, 14);
    layout->setSpacing(10);

    auto *videosLabel = new QLabel(QStringLiteral("Videos"), panel);
    videosLabel->setProperty("role", QStringLiteral("sectionTitle"));
    layout->addWidget(videosLabel);

    m_videosTable = new QTableWidget(panel);
    m_videosTable->setColumnCount(5);
    m_videosTable->setHorizontalHeaderLabels(
        {QStringLiteral("Task ID"),
         QStringLiteral("Local File"),
         QStringLiteral("Size"),
         QStringLiteral("Exists"),
         QStringLiteral("Downloaded")});
    m_videosTable->setSelectionBehavior(QAbstractItemView::SelectRows);
    m_videosTable->setSelectionMode(QAbstractItemView::SingleSelection);
    m_videosTable->setEditTriggers(QAbstractItemView::NoEditTriggers);
    m_videosTable->setAlternatingRowColors(true);
    m_videosTable->verticalHeader()->setVisible(false);
    m_videosTable->horizontalHeader()->setStretchLastSection(true);
    m_videosTable->horizontalHeader()->setSectionResizeMode(0, QHeaderView::ResizeToContents);
    m_videosTable->horizontalHeader()->setSectionResizeMode(1, QHeaderView::Stretch);
    m_videosTable->horizontalHeader()->setSectionResizeMode(2, QHeaderView::ResizeToContents);
    m_videosTable->horizontalHeader()->setSectionResizeMode(3, QHeaderView::ResizeToContents);
    m_videosTable->horizontalHeader()->setSectionResizeMode(4, QHeaderView::ResizeToContents);
    layout->addWidget(m_videosTable, 1);

    auto *videoActions = new QHBoxLayout();
    videoActions->setContentsMargins(0, 0, 0, 0);
    videoActions->setSpacing(8);
    videoActions->addStretch(1);

    m_playVideoButton = new QPushButton(QStringLiteral("Play Selected"), panel);
    m_playVideoButton->setEnabled(false);
    videoActions->addWidget(m_playVideoButton);

    m_deleteVideoButton = new QPushButton(QStringLiteral("Delete Selected"), panel);
    m_deleteVideoButton->setObjectName(QStringLiteral("dangerButton"));
    m_deleteVideoButton->setToolTip(QStringLiteral("Delete the selected local video file and remove it from Videos."));
    m_deleteVideoButton->setEnabled(false);
    videoActions->addWidget(m_deleteVideoButton);

    layout->addLayout(videoActions);

    return panel;
}

QWidget *MainWindow::buildDiagnosticsPanel()
{
    auto *panel = new QWidget(this);
    panel->setObjectName(QStringLiteral("dialogPanel"));
    auto *layout = new QVBoxLayout(panel);
    layout->setContentsMargins(14, 14, 14, 14);
    layout->setSpacing(10);

    auto *diagnosticLabel = new QLabel(QStringLiteral("Diagnostics"), panel);
    diagnosticLabel->setProperty("role", QStringLiteral("sectionTitle"));
    layout->addWidget(diagnosticLabel);

    m_diagnosticLog = new QPlainTextEdit(panel);
    m_diagnosticLog->setReadOnly(true);
    m_diagnosticLog->setMaximumBlockCount(400);
    m_diagnosticLog->setMinimumHeight(180);
    layout->addWidget(m_diagnosticLog);

    return panel;
}

void MainWindow::setupDialogs()
{
    m_configurationDialog = new QDialog(this);
    m_configurationDialog->setWindowTitle(QStringLiteral("Configuration"));
    m_configurationDialog->setModal(false);
    m_configurationDialog->resize(560, 260);
    auto *configurationLayout = new QVBoxLayout(m_configurationDialog);
    configurationLayout->setContentsMargins(0, 0, 0, 0);
    configurationLayout->addWidget(buildConfigPanel());

    m_videosDialog = new QDialog(this);
    m_videosDialog->setWindowTitle(QStringLiteral("Videos"));
    m_videosDialog->setModal(false);
    m_videosDialog->resize(920, 460);
    auto *videosLayout = new QVBoxLayout(m_videosDialog);
    videosLayout->setContentsMargins(0, 0, 0, 0);
    videosLayout->addWidget(buildVideosPanel());

    m_diagnosticsDialog = new QDialog(this);
    m_diagnosticsDialog->setWindowTitle(QStringLiteral("Diagnostics"));
    m_diagnosticsDialog->setModal(false);
    m_diagnosticsDialog->resize(900, 420);
    auto *diagnosticsLayout = new QVBoxLayout(m_diagnosticsDialog);
    diagnosticsLayout->setContentsMargins(0, 0, 0, 0);
    diagnosticsLayout->addWidget(buildDiagnosticsPanel());
}

void MainWindow::setupHiddenResultsTable()
{
    m_resultsTable = new QTableWidget(this);
    m_resultsTable->setColumnCount(5);
    m_resultsTable->setHorizontalHeaderLabels(
        {QStringLiteral("Task ID"),
         QStringLiteral("Output Path"),
         QStringLiteral("Exists"),
         QStringLiteral("Download"),
         QStringLiteral("Created")});
    m_resultsTable->setSelectionBehavior(QAbstractItemView::SelectRows);
    m_resultsTable->setSelectionMode(QAbstractItemView::SingleSelection);
    m_resultsTable->setEditTriggers(QAbstractItemView::NoEditTriggers);
    m_resultsTable->setVisible(false);
}

void MainWindow::connectSignals()
{
    connect(m_configurationButton, &QPushButton::clicked, this, &MainWindow::showConfigurationDialog);
    connect(m_videosButton, &QPushButton::clicked, this, &MainWindow::showVideosDialog);
    connect(m_diagnosticsButton, &QPushButton::clicked, this, &MainWindow::showDiagnosticsDialog);
    connect(m_applyServiceUrlButton, &QPushButton::clicked, this, &MainWindow::applyServiceUrl);
    connect(m_serviceUrlEdit, &QLineEdit::returnPressed, this, &MainWindow::applyServiceUrl);
    connect(m_sendButton, &QPushButton::clicked, this, &MainWindow::sendPrompt);
    connect(m_addImageButton, &QPushButton::clicked, this, &MainWindow::chooseInputImage);
    connect(m_removeImageButton, &QPushButton::clicked, this, &MainWindow::removeInputImage);
    connect(m_deleteTaskButton, &QPushButton::clicked, this, &MainWindow::deleteSelectedTask);
    connect(m_chooseDownloadDirectoryButton, &QPushButton::clicked, this, &MainWindow::chooseDownloadDirectory);
    connect(m_playVideoButton, &QPushButton::clicked, this, &MainWindow::playSelectedVideo);
    connect(m_deleteVideoButton, &QPushButton::clicked, this, &MainWindow::deleteSelectedVideo);
    connect(m_pollTimer, &QTimer::timeout, this, &MainWindow::pollActiveTasks);
    connect(m_tasksList, &QListWidget::itemSelectionChanged, this, [this]() {
        updateOutputDirectoryField();
        if (m_deleteTaskButton != nullptr) {
            m_deleteTaskButton->setEnabled(!selectedTaskId().isEmpty());
        }
    });
    connect(m_resultsTable, &QTableWidget::itemSelectionChanged, this, &MainWindow::updateOutputDirectoryField);
    connect(m_videosTable, &QTableWidget::itemSelectionChanged, this, [this]() {
        const bool hasSelection = !selectedVideoTaskId().isEmpty();
        if (m_playVideoButton != nullptr) {
            m_playVideoButton->setEnabled(hasSelection);
        }
        if (m_deleteVideoButton != nullptr) {
            m_deleteVideoButton->setEnabled(hasSelection);
        }
    });
    connect(m_videosTable, &QTableWidget::itemDoubleClicked, this, [this](QTableWidgetItem *) {
        playSelectedVideo();
    });
    connect(m_wslDistroEdit, &QLineEdit::textChanged, this, &MainWindow::updateOutputDirectoryField);
    connect(m_openOutputDirectoryButton, &QPushButton::clicked, this, &MainWindow::openSelectedOutputDirectory);
    connect(&m_apiClient, &ApiClient::healthChecked, this, &MainWindow::onHealthChecked);
    connect(&m_apiClient, &ApiClient::taskCreated, this, &MainWindow::onTaskCreated);
    connect(&m_apiClient, &ApiClient::taskFetched, this, &MainWindow::onTaskFetched);
    connect(&m_apiClient, &ApiClient::tasksFetched, this, &MainWindow::onTasksFetched);
    connect(&m_apiClient, &ApiClient::resultsFetched, this, &MainWindow::onResultsFetched);
    connect(&m_apiClient, &ApiClient::resultDownloaded, this, &MainWindow::onResultDownloaded);
    connect(&m_apiClient, &ApiClient::requestFailed, this, &MainWindow::onRequestFailed);

    auto *deleteTaskShortcut = new QShortcut(QKeySequence::Delete, m_tasksList);
    connect(deleteTaskShortcut, &QShortcut::activated, this, &MainWindow::deleteSelectedTask);
}

void MainWindow::applyVisualStyle()
{
    setStyleSheet(QStringLiteral(R"(
QMainWindow {
    background: #f7f7f8;
    color: #202123;
    font-family: "Segoe UI", "Microsoft YaHei UI";
    font-size: 13px;
}
QSplitter::handle {
    background: #e5e5e5;
}
QWidget#sidePanel,
QWidget#chatPanel,
QWidget#dialogPanel {
    background: #f7f7f8;
}
QLabel[role="sectionTitle"] {
    color: #202123;
    font-size: 14px;
    font-weight: 600;
    padding: 2px 2px 4px 2px;
}
QTextBrowser#chatView,
QListWidget,
QTableWidget,
QPlainTextEdit,
QLineEdit,
QComboBox {
    background: #ffffff;
    border: 1px solid #dedede;
    border-radius: 8px;
    color: #202123;
    selection-background-color: #ececec;
    selection-color: #202123;
}
QTextBrowser#chatView {
    padding: 10px;
}
QListWidget {
    padding: 2px;
    outline: none;
}
QListWidget::item {
    border: none;
    margin: 0;
}
QListWidget::item:selected {
    background: transparent;
}
QFrame#composerFrame {
    background: #ffffff;
    border: 1px solid #d9d9d9;
    border-radius: 8px;
}
QPlainTextEdit#promptEdit {
    border: none;
    border-radius: 0;
    padding: 4px;
    background: transparent;
}
QFrame#inputImagePreview {
    background: #f7f7f8;
    border: 1px solid #e3e3e3;
    border-radius: 8px;
}
QPushButton {
    background: #ffffff;
    border: 1px solid #d9d9d9;
    border-radius: 8px;
    padding: 6px 12px;
    min-height: 28px;
    color: #202123;
}
QPushButton:hover {
    background: #f3f3f3;
}
QPushButton:pressed {
    background: #e9e9e9;
}
QPushButton:disabled {
    color: #a0a0a0;
    background: #f5f5f5;
    border-color: #e6e6e6;
}
QPushButton#sendButton {
    background: #202123;
    border-color: #202123;
    color: #ffffff;
    font-weight: 600;
}
QPushButton#sendButton:hover {
    background: #343541;
}
QPushButton#iconButton {
    min-width: 32px;
    max-width: 32px;
    padding: 4px 0;
    font-size: 18px;
    font-weight: 500;
}
QPushButton#toolbarButton {
    background: transparent;
    border: 1px solid transparent;
    color: #4a4a4a;
    padding: 5px 10px;
}
QPushButton#toolbarButton:hover {
    background: #ececec;
    border-color: #ececec;
}
QPushButton#dangerButton {
    color: #8f1f1f;
    border-color: #ead0d0;
}
QPushButton#dangerButton:hover {
    background: #fff1f1;
    border-color: #e3b5b5;
}
QTableWidget {
    gridline-color: #eeeeee;
    alternate-background-color: #fafafa;
}
QHeaderView::section {
    background: #f7f7f8;
    border: none;
    border-bottom: 1px solid #e5e5e5;
    color: #6b6b6b;
    padding: 6px;
    font-weight: 600;
}
QFrame#taskCard {
    background: #ffffff;
    border: 1px solid #e1e1e1;
    border-radius: 8px;
}
QFrame#taskCard:hover {
    border-color: #cfcfcf;
}
QLabel#modePill,
QLabel#statusPill {
    border: 1px solid #e1e1e1;
    border-radius: 8px;
    padding: 3px 8px;
    background: #f7f7f8;
    color: #4a4a4a;
    font-size: 12px;
}
QLabel#modePillI2V {
    border: 1px solid #d7e7ff;
    border-radius: 8px;
    padding: 3px 8px;
    background: #eef5ff;
    color: #174f86;
    font-size: 12px;
}
QLabel#taskMeta {
    color: #6b6b6b;
    font-size: 12px;
}
QLabel#taskThumbnail {
    background: #f7f7f8;
    border: 1px solid #e5e5e5;
    border-radius: 8px;
    color: #6b6b6b;
    font-size: 11px;
}
QFrame#taskResultPreview {
    background: #f7f7f8;
    border: 1px solid #e5e5e5;
    border-radius: 8px;
}
QLabel#taskResultImage {
    background: #ffffff;
    border: 1px solid #e5e5e5;
    border-radius: 8px;
    color: #6b6b6b;
    font-size: 12px;
}
QLabel#taskPrompt {
    color: #202123;
    font-size: 13px;
}
QLabel#taskError {
    color: #a33a3a;
    font-size: 12px;
}
QProgressBar {
    background: #eeeeee;
    border: none;
    border-radius: 4px;
    height: 8px;
    text-align: center;
    color: #6b6b6b;
    font-size: 11px;
}
QProgressBar::chunk {
    background: #202123;
    border-radius: 4px;
}
QStatusBar {
    background: #f7f7f8;
    color: #6b6b6b;
}
)"));
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

    const bool hasInputImage = !m_currentInputImage.cachedPath.trimmed().isEmpty();
    if (hasInputImage && !QFileInfo::exists(m_currentInputImage.cachedPath)) {
        const QString message = QStringLiteral("Cached input image is missing: %1").arg(m_currentInputImage.cachedPath);
        appendDiagnostic(message);
        appendChatMessage(QStringLiteral("System"), message);
        showUserNotice(message);
        return;
    }

    appendChatMessage(
        QStringLiteral("User"),
        hasInputImage
            ? QStringLiteral("%1\n[Image] %2").arg(prompt, m_currentInputImage.fileName)
            : prompt);
    showUserNotice(QStringLiteral("Creating task..."));

    if (hasInputImage) {
        const InputImageAttachment attachment = m_currentInputImage;
        m_pendingImageRequests.insert(attachment.clientRequestId, attachment);
        appendDiagnostic(QStringLiteral("Submitting i2v task with size=%1 image=%2 to %3")
                             .arg(size, attachment.cachedPath, m_apiClient.baseUrl().toString()));
        m_apiClient.createImageTask(prompt, size, attachment.cachedPath, attachment.clientRequestId);
        clearCurrentInputImage(false);
    } else {
        appendDiagnostic(QStringLiteral("Submitting t2v task with size=%1 to %2")
                             .arg(size, m_apiClient.baseUrl().toString()));
        m_apiClient.createTask(prompt, size);
    }
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
        if (isDeletedTask(taskId)) {
            m_activeTaskIds.remove(taskId);
            m_inFlightTaskIds.remove(taskId);
            continue;
        }
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

void MainWindow::showConfigurationDialog()
{
    if (m_configurationDialog == nullptr) {
        return;
    }
    m_configurationDialog->show();
    m_configurationDialog->raise();
    m_configurationDialog->activateWindow();
}

void MainWindow::showVideosDialog()
{
    if (m_videosDialog == nullptr) {
        return;
    }
    refreshVideosTable();
    m_videosDialog->show();
    m_videosDialog->raise();
    m_videosDialog->activateWindow();
}

void MainWindow::showDiagnosticsDialog()
{
    if (m_diagnosticsDialog == nullptr) {
        return;
    }
    m_diagnosticsDialog->show();
    m_diagnosticsDialog->raise();
    m_diagnosticsDialog->activateWindow();
}

bool MainWindow::eventFilter(QObject *watched, QEvent *event)
{
    if (event->type() == QEvent::MouseButtonDblClick) {
        const QString taskId = watched->property("taskPreviewTaskId").toString();
        if (!taskId.isEmpty()) {
            playTaskVideo(taskId);
            return true;
        }
    }
    return QMainWindow::eventFilter(watched, event);
}

void MainWindow::chooseInputImage()
{
    const QString filePath = QFileDialog::getOpenFileName(
        this,
        QStringLiteral("Choose Input Image"),
        QDir::homePath(),
        QStringLiteral("Images (*.png *.jpg *.jpeg *.webp)"));
    if (filePath.isEmpty()) {
        return;
    }

    QString error;
    if (!setCurrentInputImage(filePath, &error)) {
        appendDiagnostic(error);
        appendChatMessage(QStringLiteral("System"), error);
        showUserNotice(error);
        return;
    }

    appendDiagnostic(QStringLiteral("Input image selected: %1 -> %2")
                         .arg(filePath, m_currentInputImage.cachedPath));
    showUserNotice(QStringLiteral("Input image attached."));
}

void MainWindow::removeInputImage()
{
    clearCurrentInputImage(true);
    appendDiagnostic(QStringLiteral("Input image removed."));
    showUserNotice(QStringLiteral("Input image removed."));
}

void MainWindow::chooseDownloadDirectory()
{
    const QString startDirectory = configuredDownloadDirectory().isEmpty()
        ? QDir::homePath()
        : configuredDownloadDirectory();
    const QString directory = QFileDialog::getExistingDirectory(
        this,
        QStringLiteral("Choose Download Directory"),
        startDirectory);
    if (directory.isEmpty()) {
        return;
    }

    QString error;
    if (!setDownloadDirectory(directory, &error)) {
        appendDiagnostic(error);
        appendChatMessage(QStringLiteral("System"), error);
        showUserNotice(error);
        return;
    }

    appendDiagnostic(QStringLiteral("Download directory set: %1").arg(configuredDownloadDirectory()));
    showUserNotice(QStringLiteral("Download directory updated."));
}

void MainWindow::deleteSelectedTask()
{
    const QString taskId = selectedTaskId();
    if (taskId.isEmpty() || !m_tasks.contains(taskId)) {
        const QString message = QStringLiteral("Select a task to delete first.");
        appendDiagnostic(message);
        showUserNotice(message);
        return;
    }

    const TaskModels::TaskDetail task = m_tasks.value(taskId);
    const QString prompt = task.prompt.simplified();
    const QString confirmText = QStringLiteral(
        "Delete this task from the client?\n\n"
        "Task ID: %1\n"
        "%2\n\n"
        "This removes local task metadata, input image cache, preview video cache, and thumbnails.\n"
        "Downloaded videos are kept and can only be deleted from Videos.")
                                    .arg(taskId, prompt.isEmpty() ? QString() : QStringLiteral("Prompt: %1").arg(prompt.left(160)));

    const QMessageBox::StandardButton answer = QMessageBox::question(
        this,
        QStringLiteral("Delete Task"),
        confirmText,
        QMessageBox::Yes | QMessageBox::Cancel,
        QMessageBox::Cancel);
    if (answer != QMessageBox::Yes) {
        return;
    }

    QString error;
    if (!deleteTaskLocalData(taskId, &error)) {
        const QString message = QStringLiteral("Failed to delete task data: %1").arg(error);
        appendDiagnostic(message);
        appendChatMessage(QStringLiteral("System"), message);
        showUserNotice(message);
        return;
    }

    m_deletedTaskIds.insert(taskId);
    saveDeletedTasks();
    refreshTasksTable();
    refreshResultsTable();
    updateOutputDirectoryField();

    const QString message = QStringLiteral("Deleted task %1. Downloaded videos were kept.").arg(taskId);
    appendDiagnostic(message);
    appendChatMessage(QStringLiteral("System"), message);
    showUserNotice(QStringLiteral("Task deleted."));
}

void MainWindow::downloadSelectedResult()
{
    const QString taskId = selectedResultTaskId();
    if (taskId.isEmpty() || !m_results.contains(taskId)) {
        const QString message = QStringLiteral("Select a result with a download URL first.");
        appendDiagnostic(message);
        showUserNotice(message);
        return;
    }

    startResultDownloadForResult(m_results.value(taskId), QStringLiteral("manual result download"));
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

    if (!isWslSharePath(directory) && !QDir(directory).exists()) {
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

void MainWindow::playSelectedVideo()
{
    const QString taskId = selectedVideoTaskId();
    if (taskId.isEmpty() || !m_downloadedVideos.contains(taskId)) {
        const QString message = QStringLiteral("Select a downloaded video first.");
        appendDiagnostic(message);
        showUserNotice(message);
        return;
    }

    const DownloadedVideo video = m_downloadedVideos.value(taskId);
    if (!QFileInfo::exists(video.localPath)) {
        const QString message = QStringLiteral("Local video file does not exist: %1").arg(video.localPath);
        appendDiagnostic(message);
        appendChatMessage(QStringLiteral("System"), message);
        showUserNotice(message);
        refreshVideosTable();
        return;
    }

    if (!QDesktopServices::openUrl(QUrl::fromLocalFile(video.localPath))) {
        const QString message = QStringLiteral("Failed to open video with the Windows default player: %1").arg(video.localPath);
        appendDiagnostic(message);
        appendChatMessage(QStringLiteral("System"), message);
        showUserNotice(message);
        return;
    }

    appendDiagnostic(QStringLiteral("Opened local video: %1").arg(video.localPath));
    showUserNotice(QStringLiteral("Opened video."));
}

void MainWindow::deleteSelectedVideo()
{
    const QString taskId = selectedVideoTaskId();
    if (taskId.isEmpty() || !m_downloadedVideos.contains(taskId)) {
        const QString message = QStringLiteral("Select a downloaded video first.");
        appendDiagnostic(message);
        showUserNotice(message);
        return;
    }

    const DownloadedVideo video = m_downloadedVideos.value(taskId);
    const QString confirmText = QStringLiteral(
        "Delete this local video?\n\n"
        "Task ID: %1\n"
        "File: %2\n\n"
        "This removes the mp4 file and the Videos index entry. The task history is kept.")
                                    .arg(taskId, video.localPath);
    const QMessageBox::StandardButton answer = QMessageBox::question(
        this,
        QStringLiteral("Delete Video"),
        confirmText,
        QMessageBox::Yes | QMessageBox::Cancel,
        QMessageBox::Cancel);
    if (answer != QMessageBox::Yes) {
        return;
    }

    if (QFileInfo::exists(video.localPath) && !QFile::remove(video.localPath)) {
        const QString message = QStringLiteral("Failed to delete local video file: %1").arg(video.localPath);
        appendDiagnostic(message);
        appendChatMessage(QStringLiteral("System"), message);
        showUserNotice(message);
        return;
    }

    m_downloadedVideos.remove(taskId);
    saveDownloadedVideos();
    refreshVideosTable();
    refreshTasksTable();

    const QString message = QStringLiteral("Deleted local video for task %1: %2").arg(taskId, video.localPath);
    appendDiagnostic(message);
    appendChatMessage(QStringLiteral("System"), message);
    showUserNotice(QStringLiteral("Video deleted."));
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
    if (isDeletedTask(task.taskId)) {
        return;
    }

    if (!task.clientRequestId.isEmpty() && m_pendingImageRequests.contains(task.clientRequestId)) {
        TaskLocalMetadata metadata;
        QString error;
        if (finalizePendingImageForTask(task, metadata, &error)) {
            m_taskMetadata.insert(task.taskId, metadata);
            saveTaskMetadata(metadata);
            appendDiagnostic(QStringLiteral("Saved task image metadata: task_id=%1 local_image=%2 server_image=%3")
                                 .arg(task.taskId, metadata.inputImageLocalPath, metadata.inputImageServerPath));
        } else {
            appendDiagnostic(error);
            appendChatMessage(QStringLiteral("System"), error);
            showUserNotice(error);
        }
    }

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
                       "mode: %2\n"
                       "status: %3\n"
                       "log_path: %4")
            .arg(task.taskId, normalizedTaskMode(task), task.status, task.logPath));
    appendDiagnostic(QStringLiteral("Task created: %1 mode=%2 status=%3")
                         .arg(task.taskId, normalizedTaskMode(task), task.status));
    refreshTasksTable();
    showUserNotice(QStringLiteral("Task created: %1").arg(task.taskId));

    if (m_smokeTestEnabled && !m_smokeImagePath.isEmpty() && !m_smokeRequiresDownload) {
        const QString metadataPath = taskMetadataPath(task.taskId);
        const bool hasMetadata = QFileInfo::exists(metadataPath);
        finishSmokeTest(
            hasMetadata && normalizedTaskMode(task) == QStringLiteral("i2v"),
            QStringLiteral("Smoke i2v task created: %1 | mode=%2 | metadata=%3 | input_image_path=%4")
                .arg(task.taskId, normalizedTaskMode(task), metadataPath, task.inputImagePath));
    }
}

void MainWindow::onTaskFetched(const TaskModels::TaskDetail &task)
{
    m_inFlightTaskIds.remove(task.taskId);
    if (isDeletedTask(task.taskId)) {
        m_activeTaskIds.remove(task.taskId);
        stopPollingIfIdle();
        return;
    }

    const TaskModels::TaskDetail previous = m_tasks.value(task.taskId);
    const bool hadPrevious = m_tasks.contains(task.taskId);
    syncTaskDetail(task);
    if (m_taskMetadata.contains(task.taskId)) {
        TaskLocalMetadata metadata = m_taskMetadata.value(task.taskId);
        bool changed = false;
        const QString mode = normalizedTaskMode(task);
        if (!mode.isEmpty() && metadata.mode != mode) {
            metadata.mode = mode;
            changed = true;
        }
        if (!task.inputImagePath.isEmpty() && metadata.inputImageServerPath != task.inputImagePath) {
            metadata.inputImageServerPath = task.inputImagePath;
            metadata.hasInputImage = true;
            changed = true;
        }
        if (changed) {
            m_taskMetadata.insert(task.taskId, metadata);
            saveTaskMetadata(metadata);
        }
    }
    refreshTasksTable();

    if (!hadPrevious || visibleTaskStateChanged(previous, task)) {
        const QString message = formatTaskUpdateMessage(task);
        appendChatMessage(QStringLiteral("System"), message);
        appendDiagnostic(QStringLiteral("Task update: %1").arg(message.simplified()));
        if (!isTerminalStatus(task.status)) {
            showUserNotice(
                QStringLiteral("Task %1: %2").arg(task.taskId.left(8), formatRuntimeSummary(task)),
                kPollIntervalMs + 1000);
        }
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
            if (!task.downloadUrl.isEmpty()) {
                summary += QStringLiteral(" | download_url=%1").arg(task.downloadUrl);
            }
            if (!task.inputImagePath.isEmpty()) {
                summary += QStringLiteral(" | input_image_path=%1").arg(task.inputImagePath);
            }
            if (!task.errorMessage.isEmpty()) {
                summary += QStringLiteral(" | error_message=%1").arg(task.errorMessage);
            }
            if (m_smokeRequiresDownload) {
                if (task.status != QStringLiteral("succeeded")) {
                    finishSmokeTest(false, summary);
                    return;
                }
                if (!startResultDownloadForTask(task, QStringLiteral("smoke download"))) {
                    finishSmokeTest(false, QStringLiteral("%1 | download did not start").arg(summary));
                }
                return;
            }
            finishSmokeTest(true, summary);
        }

        if (task.status == QStringLiteral("succeeded") && !task.downloadUrl.isEmpty()
            && !m_downloadedVideos.contains(task.taskId)) {
            startResultDownloadForTask(task, QStringLiteral("completed task auto download"));
        }
    } else {
        startPollingIfNeeded();
    }
}

void MainWindow::onTasksFetched(const TaskModels::TaskListResponse &tasks)
{
    int visibleCount = 0;
    for (const TaskModels::TaskSummary &task : tasks.items) {
        if (isDeletedTask(task.taskId)) {
            m_activeTaskIds.remove(task.taskId);
            m_inFlightTaskIds.remove(task.taskId);
            continue;
        }
        ++visibleCount;
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
    appendDiagnostic(QStringLiteral("Loaded %1 task item(s), %2 hidden by local deletion.")
                         .arg(visibleCount)
                         .arg(tasks.items.size() - visibleCount));
}

void MainWindow::onResultsFetched(const TaskModels::ResultListResponse &results)
{
    m_results.clear();
    int visibleCount = 0;
    for (const TaskModels::ResultItem &result : results.items) {
        if (isDeletedTask(result.taskId)) {
            continue;
        }
        ++visibleCount;
        syncResultItem(result);
    }

    refreshResultsTable();
    for (const TaskModels::TaskDetail &task : std::as_const(m_tasks)) {
        ensureTaskResultPreview(task);
    }
    refreshTasksTable();
    appendDiagnostic(QStringLiteral("Loaded %1 result item(s), %2 hidden by local task deletion.")
                         .arg(visibleCount)
                         .arg(results.items.size() - visibleCount));
}

void MainWindow::onResultDownloaded(const ResultDownload &download)
{
    m_downloadInFlightTaskIds.remove(download.taskId);

    if (download.purpose == QString::fromLatin1(kDownloadPurposePreview)) {
        m_previewDownloadInFlightTaskIds.remove(download.taskId);
        if (isDeletedTask(download.taskId)) {
            QFile::remove(download.localPath);
            appendDiagnostic(QStringLiteral("Discarded preview video for deleted task %1: %2")
                                 .arg(download.taskId, download.localPath));
            return;
        }
        appendDiagnostic(QStringLiteral("Downloaded preview video %1 to %2 (%3)")
                             .arg(download.taskId, download.localPath, formatFileSize(download.fileSize)));
        enqueueThumbnailGeneration(download.taskId);
        refreshTasksTable();
        return;
    }

    DownloadedVideo video;
    video.taskId = download.taskId;
    video.prompt = promptForTaskId(download.taskId);
    video.localPath = download.localPath;
    video.downloadUrl = download.url.toString();
    if (m_tasks.contains(download.taskId)) {
        video.sourceOutputPath = m_tasks.value(download.taskId).outputPath;
    } else if (m_results.contains(download.taskId)) {
        video.sourceOutputPath = m_results.value(download.taskId).outputPath;
    }
    video.createTimeRaw = createTimeRawForTaskId(download.taskId);
    video.createTime = createTimeForTaskId(download.taskId);
    video.downloadedAt = QDateTime::currentDateTimeUtc();
    video.downloadedAtRaw = video.downloadedAt.toString(Qt::ISODateWithMs);
    video.fileSize = QFileInfo(download.localPath).size();
    if (video.fileSize <= 0) {
        video.fileSize = download.fileSize;
    }

    syncDownloadedVideo(video);
    saveDownloadedVideos();
    enqueueThumbnailGeneration(download.taskId);
    refreshTasksTable();
    refreshVideosTable();

    const QString message = QStringLiteral("Downloaded video %1 to %2 (%3)")
                                .arg(download.taskId, download.localPath, formatFileSize(video.fileSize));
    appendDiagnostic(message);
    appendChatMessage(QStringLiteral("System"), message);
    showUserNotice(QStringLiteral("Video downloaded: %1").arg(download.taskId));

    if (m_smokeTestEnabled && m_smokeRequiresDownload && download.taskId == m_smokeTestTaskId) {
        finishSmokeTest(
            true,
            QStringLiteral("Smoke test downloaded result: %1 | bytes=%2 | index=%3")
                .arg(download.localPath)
                .arg(video.fileSize)
                .arg(videoIndexPath()));
    }
}

void MainWindow::onRequestFailed(const RequestFailure &failure)
{
    if (failure.kind == RequestKind::FetchTask) {
        const QString taskId = failure.url.path().section(QLatin1Char('/'), -1);
        if (!taskId.isEmpty()) {
            m_inFlightTaskIds.remove(taskId);
        }
    } else if (failure.kind == RequestKind::CreateTask && !failure.clientRequestId.isEmpty()) {
        if (m_pendingImageRequests.contains(failure.clientRequestId)) {
            const InputImageAttachment attachment = m_pendingImageRequests.take(failure.clientRequestId);
            const QString root = QFileInfo(tasksCacheRoot()).absoluteFilePath();
            const QString pending = QFileInfo(attachment.pendingDirectory).absoluteFilePath();
            if (!pending.isEmpty() && pending.startsWith(root, Qt::CaseInsensitive)) {
                QDir(attachment.pendingDirectory).removeRecursively();
            }
            appendDiagnostic(QStringLiteral("Removed pending image cache after create task failure: %1")
                                 .arg(attachment.pendingDirectory));
        }
    } else if (failure.kind == RequestKind::DownloadResult) {
        const QString taskId = failure.taskId.isEmpty()
            ? failure.url.path().section(QLatin1Char('/'), -2, -2)
            : failure.taskId;
        if (!taskId.isEmpty()) {
            m_downloadInFlightTaskIds.remove(taskId);
            if (failure.downloadPurpose == QString::fromLatin1(kDownloadPurposePreview)) {
                m_previewDownloadInFlightTaskIds.remove(taskId);
                m_thumbnailFailedTaskIds.insert(taskId);
                refreshTasksTable();
            }
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
    const bool downloadFailure = m_smokeRequiresDownload
        && failure.kind == RequestKind::DownloadResult
        && failure.url.path().section(QLatin1Char('/'), -2, -2) == m_smokeTestTaskId;
    if (createFailure || pollFailure || downloadFailure) {
        finishSmokeTest(false, message);
    }
}

void MainWindow::appendChatMessage(const QString &role, const QString &message)
{
    const QString stamp = QDateTime::currentDateTime().toString(QStringLiteral("yyyy-MM-dd HH:mm:ss"));
    const bool isUser = role.compare(QStringLiteral("User"), Qt::CaseInsensitive) == 0;
    const QString align = isUser ? QStringLiteral("right") : QStringLiteral("left");
    const QString background = isUser ? QStringLiteral("#f3f3f3") : QStringLiteral("#ffffff");
    const QString border = isUser ? QStringLiteral("#e2e2e2") : QStringLiteral("#ffffff");
    const QString html = QStringLiteral(
                             "<div style=\"margin:10px 0;\" align=\"%1\">"
                             "<table cellspacing=\"0\" cellpadding=\"0\" style=\"background:%2; border:1px solid %3; border-radius:8px;\">"
                             "<tr><td style=\"padding:8px 10px;\">"
                             "<span style=\"font-size:11px; color:#777777;\">%4 · %5</span><br/>"
                             "<span style=\"font-size:14px; color:#202123;\">%6</span>"
                             "</td></tr></table></div>")
                             .arg(align,
                                  background,
                                  border,
                                  htmlEscapeAndBreaks(stamp),
                                  htmlEscapeAndBreaks(role),
                                  htmlEscapeAndBreaks(message));
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

QString MainWindow::smokeTaskSnapshotSummary() const
{
    if (m_smokeTestTaskId.isEmpty()) {
        return QStringLiteral("Smoke test timed out before a task was created.");
    }

    QString summary = QStringLiteral("Smoke test timed out before task %1 reached a terminal state.")
                          .arg(m_smokeTestTaskId);
    if (!m_tasks.contains(m_smokeTestTaskId)) {
        return summary;
    }

    const TaskModels::TaskDetail task = m_tasks.value(m_smokeTestTaskId);
    summary += QStringLiteral(" Last observed: %1").arg(formatRuntimeSummary(task));
    if (!task.outputPath.isEmpty()) {
        summary += QStringLiteral(" | output_path=%1").arg(task.outputPath);
    }
    if (!task.errorMessage.isEmpty()) {
        summary += QStringLiteral(" | error_message=%1").arg(task.errorMessage);
    }
    if (!task.logPath.isEmpty()) {
        summary += QStringLiteral(" | log_path=%1").arg(task.logPath);
    }
    return summary;
}

void MainWindow::refreshTasksTable()
{
    const QString preservedTaskId = selectedTaskId();
    QList<TaskModels::TaskDetail> tasks = m_tasks.values();

    std::sort(tasks.begin(), tasks.end(), [](const TaskModels::TaskDetail &left, const TaskModels::TaskDetail &right) {
        return newerDateTimeFirst(left.updateTime, left.updateTimeRaw, right.updateTime, right.updateTimeRaw);
    });

    m_tasksList->clear();
    for (const TaskModels::TaskDetail &task : tasks) {
        if (isDeletedTask(task.taskId)) {
            continue;
        }
        auto *item = new QListWidgetItem();
        item->setData(Qt::UserRole, task.taskId);
        item->setToolTip(formatRuntimeSummary(task));
        const int height = task.status == QStringLiteral("succeeded")
            ? 330
            : (normalizedTaskMode(task) == QStringLiteral("i2v") ? 170 : 132);
        item->setSizeHint(QSize(360, height));
        m_tasksList->addItem(item);
        m_tasksList->setItemWidget(item, buildTaskCard(task));
    }

    if (!preservedTaskId.isEmpty()) {
        for (int row = 0; row < m_tasksList->count(); ++row) {
            QListWidgetItem *item = m_tasksList->item(row);
            if (item != nullptr && item->data(Qt::UserRole).toString() == preservedTaskId) {
                m_tasksList->setCurrentItem(item);
                break;
            }
        }
    }
    if (m_deleteTaskButton != nullptr) {
        m_deleteTaskButton->setEnabled(!selectedTaskId().isEmpty());
    }
}

QWidget *MainWindow::buildTaskCard(const TaskModels::TaskDetail &task)
{
    auto *card = new QFrame(m_tasksList);
    card->setObjectName(QStringLiteral("taskCard"));
    card->setFrameShape(QFrame::StyledPanel);
    card->setLineWidth(1);
    auto *layout = new QHBoxLayout(card);
    layout->setContentsMargins(10, 10, 10, 10);
    layout->setSpacing(10);

    const QString referenceImagePath = taskReferenceImagePath(task);
    const bool shouldShowReference = normalizedTaskMode(task) == QStringLiteral("i2v")
        || task.inputImageExists
        || !task.inputImagePath.isEmpty()
        || !referenceImagePath.isEmpty();
    if (shouldShowReference) {
        auto *thumbnail = new QLabel(card);
        thumbnail->setObjectName(QStringLiteral("taskThumbnail"));
        thumbnail->setFixedSize(84, 84);
        thumbnail->setAlignment(Qt::AlignCenter);
        thumbnail->setFrameShape(QFrame::StyledPanel);
        if (!referenceImagePath.isEmpty() && QFileInfo::exists(referenceImagePath)) {
            QPixmap pixmap(referenceImagePath);
            thumbnail->setPixmap(pixmap.scaled(thumbnail->size(), Qt::KeepAspectRatio, Qt::SmoothTransformation));
            thumbnail->setToolTip(referenceImagePath);
        } else {
            thumbnail->setText(QStringLiteral("No local\nimage"));
            thumbnail->setToolTip(QStringLiteral("The task has an input image, but the local cached copy is missing."));
        }
        layout->addWidget(thumbnail);
    }

    auto *content = new QVBoxLayout();
    content->setContentsMargins(0, 0, 0, 0);
    content->setSpacing(4);

    auto *topRow = new QHBoxLayout();
    auto *modeLabel = new QLabel(taskModeLabel(task), card);
    modeLabel->setObjectName(normalizedTaskMode(task) == QStringLiteral("i2v")
                                 ? QStringLiteral("modePillI2V")
                                 : QStringLiteral("modePill"));
    modeLabel->setMargin(4);
    topRow->addWidget(modeLabel);

    auto *statusLabel = new QLabel(task.status, card);
    statusLabel->setObjectName(QStringLiteral("statusPill"));
    statusLabel->setMargin(4);
    statusLabel->setToolTip(formatRuntimeSummary(task));
    topRow->addWidget(statusLabel);
    topRow->addStretch(1);
    auto *updatedLabel = new QLabel(formatTimestamp(task.updateTime, task.updateTimeRaw), card);
    updatedLabel->setObjectName(QStringLiteral("taskMeta"));
    topRow->addWidget(updatedLabel);
    content->addLayout(topRow);

    auto *promptLabel = new QLabel(task.prompt, card);
    promptLabel->setObjectName(QStringLiteral("taskPrompt"));
    promptLabel->setWordWrap(true);
    promptLabel->setTextInteractionFlags(Qt::TextSelectableByMouse);
    promptLabel->setToolTip(task.prompt);
    content->addWidget(promptLabel);

    if (task.status == QStringLiteral("succeeded")) {
        ensureTaskResultPreview(task);
        content->addWidget(buildTaskResultPreview(task));
    }

    auto *progress = new QProgressBar(card);
    progress->setRange(0, 100);
    progress->setValue(task.progressPercent >= 0 ? task.progressPercent : 0);
    progress->setFormat(formatProgressText(task));
    progress->setTextVisible(true);
    content->addWidget(progress);

    const QString details = QStringLiteral("%1 | %2 | task_id=%3")
                                .arg(formatStageText(task), task.size.isEmpty() ? QStringLiteral("-") : task.size, task.taskId);
    auto *detailsLabel = new QLabel(details, card);
    detailsLabel->setObjectName(QStringLiteral("taskMeta"));
    detailsLabel->setTextInteractionFlags(Qt::TextSelectableByMouse);
    detailsLabel->setToolTip(task.taskId);
    content->addWidget(detailsLabel);

    if (!task.errorMessage.isEmpty()) {
        auto *errorLabel = new QLabel(task.errorMessage, card);
        errorLabel->setObjectName(QStringLiteral("taskError"));
        errorLabel->setWordWrap(true);
        errorLabel->setToolTip(task.errorMessage);
        content->addWidget(errorLabel);
    }

    layout->addLayout(content, 1);
    return card;
}

QWidget *MainWindow::buildTaskResultPreview(const TaskModels::TaskDetail &task)
{
    auto *preview = new QFrame(m_tasksList);
    preview->setObjectName(QStringLiteral("taskResultPreview"));
    auto *layout = new QVBoxLayout(preview);
    layout->setContentsMargins(8, 8, 8, 8);
    layout->setSpacing(6);

    auto *imageLabel = new QLabel(preview);
    imageLabel->setObjectName(QStringLiteral("taskResultImage"));
    imageLabel->setMinimumSize(260, 146);
    imageLabel->setAlignment(Qt::AlignCenter);
    imageLabel->setProperty("taskPreviewTaskId", task.taskId);
    imageLabel->installEventFilter(this);

    const QString thumbnailPath = thumbnailPathForTask(task.taskId);
    if (m_previewDownloadInFlightTaskIds.contains(task.taskId)) {
        imageLabel->setText(QStringLiteral("Preparing video..."));
        imageLabel->setToolTip(QStringLiteral("Downloading the generated video for preview."));
    } else if (m_thumbnailQueuedTaskIds.contains(task.taskId) || m_thumbnailInFlightTaskIds.contains(task.taskId)) {
        imageLabel->setText(QStringLiteral("Creating preview..."));
        imageLabel->setToolTip(QStringLiteral("Extracting a representative frame."));
    } else if (isTaskThumbnailCurrent(task.taskId)) {
        QPixmap pixmap(thumbnailPath);
        imageLabel->setPixmap(pixmap.scaled(520, 292, Qt::KeepAspectRatio, Qt::SmoothTransformation));
        imageLabel->setToolTip(QStringLiteral("Double-click to play video."));
    } else if (m_thumbnailFailedTaskIds.contains(task.taskId)) {
        imageLabel->setText(QStringLiteral("Preview unavailable"));
        imageLabel->setToolTip(QStringLiteral("Preview frame extraction failed. Double-click to play if the local video is available."));
    } else {
        imageLabel->setText(QStringLiteral("Preparing preview..."));
        imageLabel->setToolTip(QStringLiteral("Waiting for the generated video preview."));
    }

    layout->addWidget(imageLabel);
    return preview;
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
        auto *downloadItem = new QTableWidgetItem(result.downloadUrl.isEmpty() ? QStringLiteral("-") : QStringLiteral("ready"));
        downloadItem->setToolTip(result.downloadUrl);
        auto *createdItem = new QTableWidgetItem(formatTimestamp(result.createTime, result.createTimeRaw));

        m_resultsTable->setItem(row, 0, taskIdItem);
        m_resultsTable->setItem(row, 1, pathItem);
        m_resultsTable->setItem(row, 2, existsItem);
        m_resultsTable->setItem(row, 3, downloadItem);
        m_resultsTable->setItem(row, 4, createdItem);
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

void MainWindow::refreshVideosTable()
{
    const QString preservedTaskId = selectedVideoTaskId();
    QList<DownloadedVideo> videos = m_downloadedVideos.values();

    std::sort(videos.begin(), videos.end(), [](const DownloadedVideo &left, const DownloadedVideo &right) {
        return newerDateTimeFirst(left.downloadedAt, left.downloadedAtRaw, right.downloadedAt, right.downloadedAtRaw);
    });

    m_videosTable->setRowCount(videos.size());
    for (int row = 0; row < videos.size(); ++row) {
        const DownloadedVideo &video = videos.at(row);
        const bool exists = QFileInfo::exists(video.localPath);
        const qint64 fileSize = exists ? QFileInfo(video.localPath).size() : video.fileSize;

        auto *taskIdItem = new QTableWidgetItem(video.taskId);
        taskIdItem->setData(Qt::UserRole, video.taskId);
        taskIdItem->setToolTip(video.prompt);
        auto *pathItem = new QTableWidgetItem(video.localPath);
        pathItem->setToolTip(video.localPath);
        auto *sizeItem = new QTableWidgetItem(formatFileSize(fileSize));
        sizeItem->setTextAlignment(Qt::AlignRight | Qt::AlignVCenter);
        auto *existsItem = new QTableWidgetItem(exists ? QStringLiteral("true") : QStringLiteral("false"));
        auto *downloadedItem = new QTableWidgetItem(formatTimestamp(video.downloadedAt, video.downloadedAtRaw));

        m_videosTable->setItem(row, 0, taskIdItem);
        m_videosTable->setItem(row, 1, pathItem);
        m_videosTable->setItem(row, 2, sizeItem);
        m_videosTable->setItem(row, 3, existsItem);
        m_videosTable->setItem(row, 4, downloadedItem);
    }

    if (!preservedTaskId.isEmpty()) {
        for (int row = 0; row < m_videosTable->rowCount(); ++row) {
            QTableWidgetItem *item = m_videosTable->item(row, 0);
            if (item != nullptr && item->data(Qt::UserRole).toString() == preservedTaskId) {
                m_videosTable->selectRow(row);
                break;
            }
        }
    }
    const bool hasSelection = !selectedVideoTaskId().isEmpty();
    if (m_playVideoButton != nullptr) {
        m_playVideoButton->setEnabled(hasSelection);
    }
    if (m_deleteVideoButton != nullptr) {
        m_deleteVideoButton->setEnabled(hasSelection);
    }
}

void MainWindow::syncTaskSummary(const TaskModels::TaskSummary &task)
{
    syncTaskDetail(summaryToDetail(task));
}

void MainWindow::syncTaskDetail(const TaskModels::TaskDetail &task)
{
    if (isDeletedTask(task.taskId)) {
        return;
    }
    m_tasks.insert(task.taskId, task);
    if (!task.taskId.isEmpty()
        && (normalizedTaskMode(task) == QStringLiteral("i2v") || !task.inputImagePath.isEmpty() || task.inputImageExists)
        && !m_taskMetadata.contains(task.taskId)) {
        TaskLocalMetadata metadata;
        metadata.taskId = task.taskId;
        metadata.prompt = task.prompt;
        metadata.mode = normalizedTaskMode(task);
        metadata.inputImageServerPath = task.inputImagePath;
        metadata.hasInputImage = true;
        metadata.createTimeRaw = task.createTimeRaw;
        metadata.createTime = task.createTime;
        m_taskMetadata.insert(task.taskId, metadata);
    }
    updateOutputDirectoryField();
}

void MainWindow::syncResultItem(const TaskModels::ResultItem &result)
{
    if (isDeletedTask(result.taskId)) {
        return;
    }
    m_results.insert(result.taskId, result);
    updateOutputDirectoryField();
}

void MainWindow::syncDownloadedVideo(const DownloadedVideo &video)
{
    m_downloadedVideos.insert(video.taskId, video);
}

QString MainWindow::selectedTaskId() const
{
    if (m_tasksList == nullptr || m_tasksList->currentItem() == nullptr) {
        return {};
    }
    return m_tasksList->currentItem()->data(Qt::UserRole).toString();
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

QString MainWindow::selectedVideoTaskId() const
{
    const QModelIndexList rows = m_videosTable->selectionModel() != nullptr
        ? m_videosTable->selectionModel()->selectedRows()
        : QModelIndexList{};
    if (rows.isEmpty()) {
        return {};
    }
    QTableWidgetItem *item = m_videosTable->item(rows.first().row(), 0);
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

void MainWindow::loadPersistentState()
{
    QSettings settings;
    const QString downloadDirectory = settings.value(QString::fromLatin1(kDownloadDirectorySetting)).toString();
    if (!downloadDirectory.trimmed().isEmpty()) {
        m_downloadDirectoryEdit->setText(downloadDirectory.trimmed());
    }

    loadDownloadedVideos();
    loadDeletedTasks();
    loadTaskMetadata();
    refreshVideosTable();
}

void MainWindow::loadDownloadedVideos()
{
    m_downloadedVideos.clear();

    QFile file(videoIndexPath());
    if (!file.exists()) {
        return;
    }
    if (!file.open(QIODevice::ReadOnly)) {
        appendDiagnostic(QStringLiteral("Failed to open local video index: %1").arg(file.errorString()));
        return;
    }

    QJsonParseError parseError;
    const QJsonDocument document = QJsonDocument::fromJson(file.readAll(), &parseError);
    if (parseError.error != QJsonParseError::NoError || !document.isObject()) {
        appendDiagnostic(QStringLiteral("Failed to parse local video index: %1").arg(parseError.errorString()));
        return;
    }

    const QJsonArray items = document.object().value(QStringLiteral("videos")).toArray();
    for (const QJsonValue &value : items) {
        if (!value.isObject()) {
            continue;
        }
        const QJsonObject object = value.toObject();
        DownloadedVideo video;
        video.taskId = object.value(QStringLiteral("task_id")).toString();
        video.prompt = object.value(QStringLiteral("prompt")).toString();
        video.localPath = object.value(QStringLiteral("local_path")).toString();
        video.downloadUrl = object.value(QStringLiteral("download_url")).toString();
        video.sourceOutputPath = object.value(QStringLiteral("source_output_path")).toString();
        video.createTimeRaw = object.value(QStringLiteral("create_time")).toString();
        video.downloadedAtRaw = object.value(QStringLiteral("downloaded_at")).toString();
        video.createTime = TaskModels::parseTimestamp(video.createTimeRaw);
        video.downloadedAt = TaskModels::parseTimestamp(video.downloadedAtRaw);
        video.fileSize = static_cast<qint64>(object.value(QStringLiteral("file_size")).toDouble(-1));
        if (!video.taskId.isEmpty() && !video.localPath.isEmpty()) {
            m_downloadedVideos.insert(video.taskId, video);
        }
    }
}

void MainWindow::saveDownloadedVideos()
{
    QJsonArray videos;
    QList<DownloadedVideo> sortedVideos = m_downloadedVideos.values();
    std::sort(sortedVideos.begin(), sortedVideos.end(), [](const DownloadedVideo &left, const DownloadedVideo &right) {
        return newerDateTimeFirst(left.downloadedAt, left.downloadedAtRaw, right.downloadedAt, right.downloadedAtRaw);
    });

    for (const DownloadedVideo &video : sortedVideos) {
        videos.append(QJsonObject{
            {QStringLiteral("task_id"), video.taskId},
            {QStringLiteral("prompt"), video.prompt},
            {QStringLiteral("local_path"), video.localPath},
            {QStringLiteral("download_url"), video.downloadUrl},
            {QStringLiteral("source_output_path"), video.sourceOutputPath},
            {QStringLiteral("create_time"), video.createTimeRaw},
            {QStringLiteral("downloaded_at"), video.downloadedAtRaw},
            {QStringLiteral("file_size"), static_cast<double>(video.fileSize)},
        });
    }

    const QString indexPath = videoIndexPath();
    QSaveFile file(indexPath);
    if (!file.open(QIODevice::WriteOnly)) {
        appendDiagnostic(QStringLiteral("Failed to open local video index for writing: %1 | path=%2")
                             .arg(file.errorString(), indexPath));
        return;
    }
    file.write(QJsonDocument(QJsonObject{{QStringLiteral("videos"), videos}}).toJson(QJsonDocument::Indented));
    if (!file.commit()) {
        appendDiagnostic(QStringLiteral("Failed to write local video index: %1 | path=%2")
                             .arg(file.errorString(), indexPath));
        return;
    }
    appendDiagnostic(QStringLiteral("Saved local video index: %1").arg(indexPath));
}

QString MainWindow::videoIndexPath() const
{
    QString root = QStandardPaths::writableLocation(QStandardPaths::AppDataLocation);
    if (root.isEmpty()) {
        root = QCoreApplication::applicationDirPath();
    }
    QDir().mkpath(root);
    return QDir(root).filePath(QString::fromLatin1(kVideoIndexFileName));
}

void MainWindow::loadDeletedTasks()
{
    m_deletedTaskIds.clear();

    QFile file(deletedTasksIndexPath());
    if (!file.exists()) {
        return;
    }
    if (!file.open(QIODevice::ReadOnly)) {
        appendDiagnostic(QStringLiteral("Failed to open deleted task index: %1").arg(file.errorString()));
        return;
    }

    QJsonParseError parseError;
    const QJsonDocument document = QJsonDocument::fromJson(file.readAll(), &parseError);
    if (parseError.error != QJsonParseError::NoError || !document.isObject()) {
        appendDiagnostic(QStringLiteral("Failed to parse deleted task index: %1").arg(parseError.errorString()));
        return;
    }

    const QJsonArray items = document.object().value(QStringLiteral("tasks")).toArray();
    for (const QJsonValue &value : items) {
        QString taskId;
        if (value.isString()) {
            taskId = value.toString();
        } else if (value.isObject()) {
            taskId = value.toObject().value(QStringLiteral("task_id")).toString();
        }
        if (!taskId.trimmed().isEmpty()) {
            m_deletedTaskIds.insert(taskId.trimmed());
        }
    }
    appendDiagnostic(QStringLiteral("Loaded %1 deleted task marker(s).").arg(m_deletedTaskIds.size()));
}

void MainWindow::saveDeletedTasks()
{
    QStringList taskIds = m_deletedTaskIds.values();
    taskIds.sort(Qt::CaseInsensitive);

    QJsonArray tasks;
    for (const QString &taskId : taskIds) {
        tasks.append(QJsonObject{
            {QStringLiteral("task_id"), taskId},
        });
    }

    const QString indexPath = deletedTasksIndexPath();
    QSaveFile file(indexPath);
    if (!file.open(QIODevice::WriteOnly)) {
        appendDiagnostic(QStringLiteral("Failed to open deleted task index for writing: %1 | path=%2")
                             .arg(file.errorString(), indexPath));
        return;
    }
    file.write(QJsonDocument(QJsonObject{{QStringLiteral("tasks"), tasks}}).toJson(QJsonDocument::Indented));
    if (!file.commit()) {
        appendDiagnostic(QStringLiteral("Failed to write deleted task index: %1 | path=%2")
                             .arg(file.errorString(), indexPath));
        return;
    }
    appendDiagnostic(QStringLiteral("Saved deleted task index: %1").arg(indexPath));
}

QString MainWindow::deletedTasksIndexPath() const
{
    QString root = QStandardPaths::writableLocation(QStandardPaths::AppDataLocation);
    if (root.isEmpty()) {
        root = QCoreApplication::applicationDirPath();
    }
    QDir().mkpath(root);
    return QDir(root).filePath(QString::fromLatin1(kDeletedTasksFileName));
}

bool MainWindow::isDeletedTask(const QString &taskId) const
{
    return m_deletedTaskIds.contains(taskId.trimmed());
}

void MainWindow::loadTaskMetadata()
{
    m_taskMetadata.clear();

    QDir root(tasksCacheRoot());
    const QFileInfoList dirs = root.entryInfoList(QDir::Dirs | QDir::NoDotAndDotDot);
    for (const QFileInfo &dirInfo : dirs) {
        restoreTaskMetadataFromFile(QDir(dirInfo.absoluteFilePath()).filePath(QString::fromLatin1(kTaskMetadataFileName)));
    }
    appendDiagnostic(QStringLiteral("Loaded %1 task metadata item(s).").arg(m_taskMetadata.size()));
}

void MainWindow::saveTaskMetadata(const TaskLocalMetadata &metadata)
{
    if (metadata.taskId.trimmed().isEmpty()) {
        appendDiagnostic(QStringLiteral("Skipped task metadata save because task_id is empty."));
        return;
    }

    const QString directory = taskCacheDirectory(metadata.taskId);
    QDir().mkpath(directory);
    const QString metadataPath = metadataPathForDirectory(directory);
    QSaveFile file(metadataPath);
    if (!file.open(QIODevice::WriteOnly)) {
        appendDiagnostic(QStringLiteral("Failed to open task metadata for writing: %1 | path=%2")
                             .arg(file.errorString(), metadataPath));
        return;
    }

    const QJsonObject object{
        {QStringLiteral("task_id"), metadata.taskId},
        {QStringLiteral("client_request_id"), metadata.clientRequestId},
        {QStringLiteral("prompt"), metadata.prompt},
        {QStringLiteral("mode"), metadata.mode},
        {QStringLiteral("input_image_local_path"), metadata.inputImageLocalPath},
        {QStringLiteral("input_image_server_path"), metadata.inputImageServerPath},
        {QStringLiteral("has_input_image"), metadata.hasInputImage},
        {QStringLiteral("create_time"), metadata.createTimeRaw},
    };
    file.write(QJsonDocument(object).toJson(QJsonDocument::Indented));
    if (!file.commit()) {
        appendDiagnostic(QStringLiteral("Failed to write task metadata: %1 | path=%2")
                             .arg(file.errorString(), metadataPath));
    }
}

bool MainWindow::restoreTaskMetadataFromFile(const QString &metadataPath)
{
    QFile file(metadataPath);
    if (!file.exists()) {
        return false;
    }
    if (!file.open(QIODevice::ReadOnly)) {
        appendDiagnostic(QStringLiteral("Failed to open task metadata: %1 | path=%2")
                             .arg(file.errorString(), metadataPath));
        return false;
    }

    QJsonParseError parseError;
    const QJsonDocument document = QJsonDocument::fromJson(file.readAll(), &parseError);
    if (parseError.error != QJsonParseError::NoError || !document.isObject()) {
        appendDiagnostic(QStringLiteral("Failed to parse task metadata: %1 | path=%2")
                             .arg(parseError.errorString(), metadataPath));
        return false;
    }

    const QJsonObject object = document.object();
    TaskLocalMetadata metadata;
    metadata.taskId = object.value(QStringLiteral("task_id")).toString();
    metadata.clientRequestId = object.value(QStringLiteral("client_request_id")).toString();
    metadata.prompt = object.value(QStringLiteral("prompt")).toString();
    metadata.mode = object.value(QStringLiteral("mode")).toString();
    metadata.inputImageLocalPath = object.value(QStringLiteral("input_image_local_path")).toString();
    metadata.inputImageServerPath = object.value(QStringLiteral("input_image_server_path")).toString();
    metadata.hasInputImage = object.value(QStringLiteral("has_input_image")).toBool(false);
    metadata.createTimeRaw = object.value(QStringLiteral("create_time")).toString();
    metadata.createTime = TaskModels::parseTimestamp(metadata.createTimeRaw);
    if (metadata.taskId.isEmpty()) {
        appendDiagnostic(QStringLiteral("Ignored task metadata without task_id: %1").arg(metadataPath));
        return false;
    }
    if (isDeletedTask(metadata.taskId)) {
        return false;
    }

    m_taskMetadata.insert(metadata.taskId, metadata);
    return true;
}

QString MainWindow::tasksCacheRoot() const
{
    QString root = qEnvironmentVariable("LOCALAPPDATA");
    if (root.isEmpty()) {
        root = QStandardPaths::writableLocation(QStandardPaths::AppLocalDataLocation);
    } else {
        root = QDir(root).filePath(QStringLiteral("VideoGenProject"));
    }
    if (root.isEmpty()) {
        root = QCoreApplication::applicationDirPath();
    }
    const QString tasksRoot = QDir(root).filePath(QStringLiteral("tasks"));
    QDir().mkpath(tasksRoot);
    return tasksRoot;
}

QString MainWindow::taskCacheDirectory(const QString &taskId) const
{
    return QDir(tasksCacheRoot()).filePath(taskId.trimmed());
}

QString MainWindow::pendingTaskCacheDirectory(const QString &clientRequestId) const
{
    return QDir(tasksCacheRoot()).filePath(QStringLiteral("pending_%1").arg(clientRequestId.trimmed()));
}

QString MainWindow::taskMetadataPath(const QString &taskId) const
{
    return metadataPathForDirectory(taskCacheDirectory(taskId));
}

QString MainWindow::metadataPathForDirectory(const QString &directory) const
{
    return QDir(directory).filePath(QString::fromLatin1(kTaskMetadataFileName));
}

bool MainWindow::validateInputImagePath(const QString &sourcePath, QString &extension, qint64 &fileSize, QString *error) const
{
    const QFileInfo info(sourcePath.trimmed());
    if (!info.exists() || !info.isFile()) {
        if (error != nullptr) {
            *error = QStringLiteral("Image file does not exist: %1").arg(sourcePath.trimmed());
        }
        return false;
    }
    if (!info.isReadable()) {
        if (error != nullptr) {
            *error = QStringLiteral("Image file is not readable: %1").arg(info.absoluteFilePath());
        }
        return false;
    }

    extension = info.suffix().toLower();
    if (extension != QStringLiteral("png")
        && extension != QStringLiteral("jpg")
        && extension != QStringLiteral("jpeg")
        && extension != QStringLiteral("webp")) {
        if (error != nullptr) {
            *error = QStringLiteral("Unsupported image format '.%1'. Supported formats: png, jpg, jpeg, webp.").arg(extension);
        }
        return false;
    }

    fileSize = info.size();
    if (fileSize > kMaxInputImageBytes) {
        if (error != nullptr) {
            *error = QStringLiteral("Image is too large: %1. Maximum allowed size is 20 MiB.")
                         .arg(formatFileSize(fileSize));
        }
        return false;
    }

    QImageReader reader(info.absoluteFilePath());
    if (!reader.canRead()) {
        if (error != nullptr) {
            *error = QStringLiteral("Selected file is not a readable image: %1").arg(info.absoluteFilePath());
        }
        return false;
    }

    if (error != nullptr) {
        error->clear();
    }
    return true;
}

bool MainWindow::prepareInputImageAttachment(const QString &sourcePath, InputImageAttachment &attachment, QString *error)
{
    QString extension;
    qint64 fileSize = 0;
    if (!validateInputImagePath(sourcePath, extension, fileSize, error)) {
        return false;
    }

    const QFileInfo sourceInfo(sourcePath.trimmed());
    const QString clientRequestId = cleanUuid();
    const QString pendingDirectory = pendingTaskCacheDirectory(clientRequestId);
    if (!QDir().mkpath(pendingDirectory)) {
        if (error != nullptr) {
            *error = QStringLiteral("Failed to create local task cache directory: %1").arg(pendingDirectory);
        }
        return false;
    }

    const QString cachedPath = QDir(pendingDirectory).filePath(imageFileNameForExtension(extension));
    QFile::remove(cachedPath);
    if (!QFile::copy(sourceInfo.absoluteFilePath(), cachedPath)) {
        if (error != nullptr) {
            *error = QStringLiteral("Failed to copy image into local task cache: %1").arg(cachedPath);
        }
        return false;
    }

    attachment = {};
    attachment.clientRequestId = clientRequestId;
    attachment.sourcePath = sourceInfo.absoluteFilePath();
    attachment.cachedPath = cachedPath;
    attachment.pendingDirectory = pendingDirectory;
    attachment.fileName = sourceInfo.fileName();
    attachment.extension = extension;
    attachment.fileSize = fileSize;
    if (error != nullptr) {
        error->clear();
    }
    return true;
}

bool MainWindow::setCurrentInputImage(const QString &sourcePath, QString *error)
{
    InputImageAttachment attachment;
    if (!prepareInputImageAttachment(sourcePath, attachment, error)) {
        return false;
    }

    clearCurrentInputImage(true);
    m_currentInputImage = attachment;
    updateInputImagePreview();
    return true;
}

void MainWindow::clearCurrentInputImage(bool removeCachedFile)
{
    if (removeCachedFile && !m_currentInputImage.pendingDirectory.isEmpty()) {
        const QString root = QFileInfo(tasksCacheRoot()).absoluteFilePath();
        const QString pending = QFileInfo(m_currentInputImage.pendingDirectory).absoluteFilePath();
        if (pending.startsWith(root, Qt::CaseInsensitive)) {
            QDir(m_currentInputImage.pendingDirectory).removeRecursively();
        }
    }
    m_currentInputImage = {};
    updateInputImagePreview();
}

void MainWindow::updateInputImagePreview()
{
    const bool hasImage = !m_currentInputImage.cachedPath.isEmpty();
    if (m_inputImagePreview != nullptr) {
        m_inputImagePreview->setVisible(hasImage);
    }
    if (!hasImage) {
        if (m_inputImageThumbnail != nullptr) {
            m_inputImageThumbnail->clear();
        }
        if (m_inputImageNameLabel != nullptr) {
            m_inputImageNameLabel->clear();
        }
        return;
    }

    if (m_inputImageThumbnail != nullptr) {
        QPixmap pixmap(m_currentInputImage.cachedPath);
        m_inputImageThumbnail->setPixmap(
            pixmap.scaled(m_inputImageThumbnail->size(), Qt::KeepAspectRatio, Qt::SmoothTransformation));
        m_inputImageThumbnail->setToolTip(m_currentInputImage.cachedPath);
    }
    if (m_inputImageNameLabel != nullptr) {
        m_inputImageNameLabel->setText(
            QStringLiteral("%1\n%2")
                .arg(m_currentInputImage.fileName, formatFileSize(m_currentInputImage.fileSize)));
        m_inputImageNameLabel->setToolTip(m_currentInputImage.cachedPath);
    }
}

bool MainWindow::finalizePendingImageForTask(const TaskModels::TaskSummary &task, TaskLocalMetadata &metadata, QString *error)
{
    if (task.clientRequestId.isEmpty() || !m_pendingImageRequests.contains(task.clientRequestId)) {
        if (error != nullptr) {
            *error = QStringLiteral("No pending image cache was found for created task %1.").arg(task.taskId);
        }
        return false;
    }

    InputImageAttachment attachment = m_pendingImageRequests.take(task.clientRequestId);
    const QString finalDirectory = taskCacheDirectory(task.taskId);
    if (!QDir().mkpath(finalDirectory)) {
        if (error != nullptr) {
            *error = QStringLiteral("Failed to create final task cache directory: %1").arg(finalDirectory);
        }
        return false;
    }

    const QString finalImagePath = QDir(finalDirectory).filePath(imageFileNameForExtension(attachment.extension));
    QFile::remove(finalImagePath);
    bool moved = QFile::rename(attachment.cachedPath, finalImagePath);
    if (!moved) {
        moved = QFile::copy(attachment.cachedPath, finalImagePath);
        if (moved) {
            QFile::remove(attachment.cachedPath);
        }
    }
    if (!moved) {
        if (error != nullptr) {
            *error = QStringLiteral("Failed to move cached input image into task directory: %1 -> %2")
                         .arg(attachment.cachedPath, finalImagePath);
        }
        return false;
    }
    QDir(attachment.pendingDirectory).removeRecursively();

    metadata = {};
    metadata.taskId = task.taskId;
    metadata.clientRequestId = task.clientRequestId;
    metadata.prompt = task.prompt;
    metadata.mode = normalizedTaskMode(task);
    metadata.inputImageLocalPath = finalImagePath;
    metadata.inputImageServerPath = task.inputImagePath;
    metadata.hasInputImage = true;
    metadata.createTimeRaw = task.createTimeRaw;
    metadata.createTime = task.createTime;
    if (error != nullptr) {
        error->clear();
    }
    return true;
}

QString MainWindow::taskReferenceImagePath(const TaskModels::TaskDetail &task) const
{
    if (m_taskMetadata.contains(task.taskId)) {
        const QString localPath = m_taskMetadata.value(task.taskId).inputImageLocalPath;
        if (!localPath.isEmpty()) {
            return localPath;
        }
    }

    const QDir dir(taskCacheDirectory(task.taskId));
    const QStringList candidates{
        QStringLiteral("input_image.png"),
        QStringLiteral("input_image.jpg"),
        QStringLiteral("input_image.jpeg"),
        QStringLiteral("input_image.webp"),
    };
    for (const QString &candidate : candidates) {
        const QString path = dir.filePath(candidate);
        if (QFileInfo::exists(path)) {
            return path;
        }
    }
    return {};
}

QString MainWindow::taskModeLabel(const TaskModels::TaskDetail &task) const
{
    return normalizedTaskMode(task) == QStringLiteral("i2v")
        ? QStringLiteral("图文生成")
        : QStringLiteral("文生视频");
}

QString MainWindow::thumbnailPathForTask(const QString &taskId) const
{
    return QDir(taskCacheDirectory(taskId)).filePath(QString::fromLatin1(kThumbnailFileName));
}

QString MainWindow::thumbnailVersionPathForTask(const QString &taskId) const
{
    return QDir(taskCacheDirectory(taskId)).filePath(QString::fromLatin1(kThumbnailVersionFileName));
}

bool MainWindow::isTaskThumbnailCurrent(const QString &taskId) const
{
    if (!QFileInfo::exists(thumbnailPathForTask(taskId))) {
        return false;
    }

    QFile versionFile(thumbnailVersionPathForTask(taskId));
    if (!versionFile.open(QIODevice::ReadOnly)) {
        return false;
    }
    return QString::fromUtf8(versionFile.readAll()).trimmed() == QString::fromLatin1(kThumbnailVersion);
}

void MainWindow::writeTaskThumbnailVersion(const QString &taskId)
{
    const QString versionPath = thumbnailVersionPathForTask(taskId);
    QDir().mkpath(QFileInfo(versionPath).absolutePath());
    QSaveFile file(versionPath);
    if (!file.open(QIODevice::WriteOnly | QIODevice::Truncate)) {
        appendDiagnostic(QStringLiteral("Failed to open thumbnail version file: %1 | path=%2")
                             .arg(file.errorString(), versionPath));
        return;
    }
    file.write(QByteArray(kThumbnailVersion));
    if (!file.commit()) {
        appendDiagnostic(QStringLiteral("Failed to write thumbnail version file: %1 | path=%2")
                             .arg(file.errorString(), versionPath));
    }
}

QString MainWindow::previewVideoPathForTask(const QString &taskId) const
{
    return QDir(taskCacheDirectory(taskId)).filePath(QString::fromLatin1(kPreviewVideoFileName));
}

QString MainWindow::localVideoPathForPreview(const QString &taskId) const
{
    if (m_downloadedVideos.contains(taskId)) {
        const QString localPath = m_downloadedVideos.value(taskId).localPath;
        if (QFileInfo::exists(localPath)) {
            return localPath;
        }
    }

    const QString previewPath = previewVideoPathForTask(taskId);
    if (QFileInfo::exists(previewPath)) {
        return previewPath;
    }
    return {};
}

void MainWindow::ensureTaskResultPreview(const TaskModels::TaskDetail &task)
{
    if (task.status != QStringLiteral("succeeded") || task.taskId.isEmpty() || isDeletedTask(task.taskId)) {
        return;
    }
    if (isTaskThumbnailCurrent(task.taskId)
        || m_thumbnailQueuedTaskIds.contains(task.taskId)
        || m_thumbnailInFlightTaskIds.contains(task.taskId)
        || m_previewDownloadInFlightTaskIds.contains(task.taskId)) {
        return;
    }

    const QString videoPath = localVideoPathForPreview(task.taskId);
    if (!videoPath.isEmpty()) {
        enqueueThumbnailGeneration(task.taskId);
        return;
    }

    if (!downloadUrlForTaskId(task.taskId).isEmpty()) {
        startPreviewDownloadForTask(task, QStringLiteral("task card preview"));
    }
}

bool MainWindow::startPreviewDownloadForTask(const TaskModels::TaskDetail &task, const QString &reason)
{
    if (task.taskId.isEmpty()
        || isDeletedTask(task.taskId)
        || m_previewDownloadInFlightTaskIds.contains(task.taskId)
        || m_downloadInFlightTaskIds.contains(task.taskId)) {
        return false;
    }

    const QString downloadUrl = downloadUrlForTaskId(task.taskId);
    if (downloadUrl.isEmpty()) {
        appendDiagnostic(QStringLiteral("Preview unavailable because task %1 has no download URL.").arg(task.taskId));
        return false;
    }

    const QString localPath = previewVideoPathForTask(task.taskId);
    QDir().mkpath(QFileInfo(localPath).absolutePath());
    m_previewDownloadInFlightTaskIds.insert(task.taskId);
    m_downloadInFlightTaskIds.insert(task.taskId);
    appendDiagnostic(QStringLiteral("Downloading preview video for task %1 to %2 (%3).")
                         .arg(task.taskId, localPath, reason));
    m_apiClient.downloadResult(task.taskId, QUrl(downloadUrl), localPath, QString::fromLatin1(kDownloadPurposePreview));
    return true;
}

void MainWindow::enqueueThumbnailGeneration(const QString &taskId)
{
    if (taskId.trimmed().isEmpty()
        || isDeletedTask(taskId)
        || isTaskThumbnailCurrent(taskId)
        || m_thumbnailQueuedTaskIds.contains(taskId)
        || m_thumbnailInFlightTaskIds.contains(taskId)
        || m_thumbnailFailedTaskIds.contains(taskId)) {
        return;
    }

    if (localVideoPathForPreview(taskId).isEmpty()) {
        return;
    }

    if (QFileInfo::exists(thumbnailPathForTask(taskId))) {
        QFile::remove(thumbnailPathForTask(taskId));
        QFile::remove(thumbnailVersionPathForTask(taskId));
    }

    m_thumbnailQueuedTaskIds.insert(taskId);
    m_thumbnailQueue.append(taskId);
    startNextThumbnailGeneration();
}

void MainWindow::startNextThumbnailGeneration()
{
    if (!m_currentThumbnailTaskId.isEmpty() || m_thumbnailQueue.isEmpty()) {
        return;
    }

    const QString taskId = m_thumbnailQueue.takeFirst();
    m_thumbnailQueuedTaskIds.remove(taskId);
    const QString videoPath = localVideoPathForPreview(taskId);
    if (videoPath.isEmpty()) {
        m_thumbnailFailedTaskIds.insert(taskId);
        startNextThumbnailGeneration();
        return;
    }

    m_currentThumbnailTaskId = taskId;
    m_thumbnailInFlightTaskIds.insert(taskId);
    appendDiagnostic(QStringLiteral("Extracting preview frame for task %1 from %2.").arg(taskId, videoPath));

    auto *context = new QObject(this);
    auto *player = new QMediaPlayer(context);
    auto *sink = new QVideoSink(context);
    player->setVideoSink(sink);
    context->setProperty("finished", false);
    context->setProperty("acceptFrames", false);
    context->setProperty("seekRequested", false);
    context->setProperty("targetPosition", 1000);

    auto enableFrameCapture = [context]() {
        if (!context->property("finished").toBool()) {
            context->setProperty("acceptFrames", true);
        }
    };

    auto requestSeek = [context, player, enableFrameCapture]() {
        if (context->property("finished").toBool() || context->property("seekRequested").toBool()) {
            return;
        }
        context->setProperty("seekRequested", true);
        context->setProperty("acceptFrames", false);
        player->setPosition(context->property("targetPosition").toLongLong());
        player->play();
        QTimer::singleShot(900, context, enableFrameCapture);
    };

    auto finish = [this, context, player, taskId](bool success, const QString &details) {
        if (context->property("finished").toBool()) {
            return;
        }
        context->setProperty("finished", true);
        player->stop();
        player->setSource(QUrl());
        context->deleteLater();
        finishThumbnailGeneration(success, details);
    };

    connect(player, &QMediaPlayer::durationChanged, context, [context](qint64 duration) {
        if (duration > 0) {
            context->setProperty("targetPosition", qBound<qint64>(250ll, duration / 3, 1500ll));
        }
    });
    connect(player, &QMediaPlayer::mediaStatusChanged, context, [context, requestSeek, finish](QMediaPlayer::MediaStatus status) {
        if (context->property("finished").toBool()) {
            return;
        }
        if (status == QMediaPlayer::LoadedMedia || status == QMediaPlayer::BufferedMedia) {
            requestSeek();
        } else if (status == QMediaPlayer::EndOfMedia || status == QMediaPlayer::InvalidMedia) {
            finish(false, QStringLiteral("Thumbnail generation ended before a usable video frame was decoded."));
        }
    });
    connect(player, &QMediaPlayer::positionChanged, context, [context](qint64 position) {
        if (context->property("finished").toBool() || !context->property("seekRequested").toBool()) {
            return;
        }
        const qint64 targetPosition = context->property("targetPosition").toLongLong();
        if (position >= qMax<qint64>(0, targetPosition - 120)) {
            context->setProperty("acceptFrames", true);
        }
    });
    connect(player, &QMediaPlayer::errorOccurred, context, [finish](QMediaPlayer::Error, const QString &errorString) {
        finish(false, QStringLiteral("Thumbnail generation failed: %1").arg(errorString));
    });
    connect(sink, &QVideoSink::videoFrameChanged, context, [this, context, taskId, finish](const QVideoFrame &frame) {
        if (context->property("finished").toBool()
            || !context->property("acceptFrames").toBool()
            || !frame.isValid()) {
            return;
        }
        const QImage image = frame.toImage();
        if (image.isNull()) {
            return;
        }
        const QString thumbnailPath = thumbnailPathForTask(taskId);
        QDir().mkpath(QFileInfo(thumbnailPath).absolutePath());
        QFile::remove(thumbnailPath);
        const bool saved = image.scaled(720, 405, Qt::KeepAspectRatioByExpanding, Qt::SmoothTransformation)
                               .save(thumbnailPath, "PNG");
        if (saved) {
            writeTaskThumbnailVersion(taskId);
        }
        finish(
            saved,
            saved
                ? QStringLiteral("Saved task thumbnail: %1").arg(thumbnailPath)
                : QStringLiteral("Failed to save task thumbnail: %1").arg(thumbnailPath));
    });
    QTimer::singleShot(6000, context, [finish]() {
        finish(false, QStringLiteral("Thumbnail generation timed out before a usable video frame was decoded."));
    });
    QTimer::singleShot(300, context, requestSeek);
    QTimer::singleShot(1500, context, enableFrameCapture);

    player->setSource(QUrl::fromLocalFile(videoPath));
    player->play();
}

void MainWindow::finishThumbnailGeneration(bool success, const QString &details)
{
    if (m_currentThumbnailTaskId.isEmpty()) {
        return;
    }

    const QString taskId = m_currentThumbnailTaskId;
    m_thumbnailInFlightTaskIds.remove(taskId);
    if (!success) {
        m_thumbnailFailedTaskIds.insert(taskId);
    }
    m_currentThumbnailTaskId.clear();
    appendDiagnostic(details);
    refreshTasksTable();
    startNextThumbnailGeneration();
}

void MainWindow::playTaskVideo(const QString &taskId)
{
    const QString videoPath = localVideoPathForPreview(taskId);
    if (videoPath.isEmpty() || !QFileInfo::exists(videoPath)) {
        const QString message = m_previewDownloadInFlightTaskIds.contains(taskId)
            ? QStringLiteral("Video is still being prepared for task %1.").arg(taskId)
            : QStringLiteral("No local video is available for task %1 yet.").arg(taskId);
        appendDiagnostic(message);
        showUserNotice(message);
        return;
    }

    if (!QDesktopServices::openUrl(QUrl::fromLocalFile(videoPath))) {
        const QString message = QStringLiteral("Failed to open task video with the Windows default player: %1").arg(videoPath);
        appendDiagnostic(message);
        appendChatMessage(QStringLiteral("System"), message);
        showUserNotice(message);
        return;
    }

    appendDiagnostic(QStringLiteral("Opened task video: %1").arg(videoPath));
    showUserNotice(QStringLiteral("Opened video."));
}

bool MainWindow::deleteTaskLocalData(const QString &taskId, QString *error)
{
    const QString trimmedTaskId = taskId.trimmed();
    if (trimmedTaskId.isEmpty()) {
        if (error != nullptr) {
            *error = QStringLiteral("Task id is empty.");
        }
        return false;
    }

    QStringList preservedVideos;
    if (!removeTaskCacheDirectory(trimmedTaskId, &preservedVideos, error)) {
        return false;
    }

    m_tasks.remove(trimmedTaskId);
    m_results.remove(trimmedTaskId);
    m_taskMetadata.remove(trimmedTaskId);
    m_activeTaskIds.remove(trimmedTaskId);
    m_inFlightTaskIds.remove(trimmedTaskId);
    m_previewDownloadInFlightTaskIds.remove(trimmedTaskId);
    m_thumbnailQueuedTaskIds.remove(trimmedTaskId);
    m_thumbnailInFlightTaskIds.remove(trimmedTaskId);
    m_thumbnailFailedTaskIds.remove(trimmedTaskId);
    m_thumbnailQueue.removeAll(trimmedTaskId);
    stopPollingIfIdle();

    if (!preservedVideos.isEmpty()) {
        appendDiagnostic(QStringLiteral("Preserved %1 downloaded video file(s) while deleting task %2.")
                             .arg(preservedVideos.size())
                             .arg(trimmedTaskId));
    }

    if (error != nullptr) {
        error->clear();
    }
    return true;
}

bool MainWindow::removeTaskCacheDirectory(const QString &taskId, QStringList *preservedVideos, QString *error)
{
    const QString cacheDirectory = taskCacheDirectory(taskId);
    const QFileInfo cacheInfo(cacheDirectory);
    if (!cacheInfo.exists()) {
        if (error != nullptr) {
            error->clear();
        }
        return true;
    }
    if (!cacheInfo.isDir()) {
        if (error != nullptr) {
            *error = QStringLiteral("Task cache path is not a directory: %1").arg(cacheDirectory);
        }
        return false;
    }

    const QString root = normalizedAbsolutePath(tasksCacheRoot());
    const QString target = normalizedAbsolutePath(cacheDirectory);
    if (target.compare(root, Qt::CaseInsensitive) == 0 || !pathIsAtOrUnderDirectory(target, root)) {
        if (error != nullptr) {
            *error = QStringLiteral("Refusing to delete path outside task cache root: %1").arg(target);
        }
        return false;
    }

    QSet<QString> preservedVideoPaths;
    for (const DownloadedVideo &video : std::as_const(m_downloadedVideos)) {
        if (video.localPath.trimmed().isEmpty()) {
            continue;
        }
        const QString videoPath = normalizedAbsolutePath(video.localPath);
        if (pathIsAtOrUnderDirectory(videoPath, target)) {
            preservedVideoPaths.insert(videoPath);
        }
    }

    if (preservedVideoPaths.isEmpty()) {
        if (!QDir(cacheDirectory).removeRecursively()) {
            if (error != nullptr) {
                *error = QStringLiteral("Failed to remove task cache directory: %1").arg(cacheDirectory);
            }
            return false;
        }
        if (error != nullptr) {
            error->clear();
        }
        return true;
    }

    QStringList directories;
    QDirIterator iterator(
        cacheDirectory,
        QDir::AllEntries | QDir::NoDotAndDotDot | QDir::Hidden | QDir::System,
        QDirIterator::Subdirectories);
    while (iterator.hasNext()) {
        iterator.next();
        const QFileInfo entry = iterator.fileInfo();
        const QString entryPath = normalizedAbsolutePath(entry.absoluteFilePath());
        if (entry.isDir()) {
            directories.append(entry.absoluteFilePath());
            continue;
        }
        if (preservedVideoPaths.contains(entryPath)) {
            if (preservedVideos != nullptr) {
                preservedVideos->append(entry.absoluteFilePath());
            }
            continue;
        }
        if (!QFile::remove(entry.absoluteFilePath())) {
            if (error != nullptr) {
                *error = QStringLiteral("Failed to remove task cache file: %1").arg(entry.absoluteFilePath());
            }
            return false;
        }
    }

    std::sort(directories.begin(), directories.end(), [](const QString &left, const QString &right) {
        return left.size() > right.size();
    });
    for (const QString &directory : directories) {
        QDir().rmdir(directory);
    }
    QDir().rmdir(cacheDirectory);

    if (error != nullptr) {
        error->clear();
    }
    return true;
}

QString MainWindow::configuredDownloadDirectory() const
{
    return m_downloadDirectoryEdit != nullptr ? m_downloadDirectoryEdit->text().trimmed() : QString{};
}

bool MainWindow::setDownloadDirectory(const QString &directory, QString *error)
{
    const QString cleaned = directory.trimmed();
    if (cleaned.isEmpty()) {
        if (error != nullptr) {
            *error = QStringLiteral("Download directory is empty.");
        }
        return false;
    }

    QDir dir(cleaned);
    if (!dir.exists() && !dir.mkpath(QStringLiteral("."))) {
        if (error != nullptr) {
            *error = QStringLiteral("Failed to create download directory: %1").arg(cleaned);
        }
        return false;
    }

    const QString absolutePath = QFileInfo(dir.absolutePath()).absoluteFilePath();
    if (!QFileInfo(absolutePath).isDir()) {
        if (error != nullptr) {
            *error = QStringLiteral("Download path is not a directory: %1").arg(absolutePath);
        }
        return false;
    }

    if (m_downloadDirectoryEdit != nullptr) {
        m_downloadDirectoryEdit->setText(absolutePath);
    }
    QSettings settings;
    settings.setValue(QString::fromLatin1(kDownloadDirectorySetting), absolutePath);
    if (error != nullptr) {
        error->clear();
    }
    return true;
}

bool MainWindow::ensureDownloadDirectory(QString &directory)
{
    QString configured = configuredDownloadDirectory();
    if (configured.isEmpty()) {
        configured = QFileDialog::getExistingDirectory(
            this,
            QStringLiteral("Choose Download Directory"),
            QDir::homePath());
        if (configured.isEmpty()) {
            appendDiagnostic(QStringLiteral("Download canceled because no local directory was selected."));
            return false;
        }
    }

    QString error;
    if (!setDownloadDirectory(configured, &error)) {
        appendDiagnostic(error);
        appendChatMessage(QStringLiteral("System"), error);
        showUserNotice(error);
        return false;
    }

    directory = configuredDownloadDirectory();
    return true;
}

QString MainWindow::localVideoPathForTask(const QString &taskId) const
{
    const QString directory = configuredDownloadDirectory();
    if (directory.isEmpty()) {
        return {};
    }
    return QDir(directory).filePath(taskVideoFileName(taskId));
}

QString MainWindow::downloadUrlForTaskId(const QString &taskId) const
{
    if (m_tasks.contains(taskId) && !m_tasks.value(taskId).downloadUrl.isEmpty()) {
        return m_tasks.value(taskId).downloadUrl;
    }
    if (m_results.contains(taskId)) {
        return m_results.value(taskId).downloadUrl;
    }
    return {};
}

QString MainWindow::promptForTaskId(const QString &taskId) const
{
    if (m_tasks.contains(taskId)) {
        return m_tasks.value(taskId).prompt;
    }
    return {};
}

QString MainWindow::createTimeRawForTaskId(const QString &taskId) const
{
    if (m_tasks.contains(taskId)) {
        return m_tasks.value(taskId).createTimeRaw;
    }
    if (m_results.contains(taskId)) {
        return m_results.value(taskId).createTimeRaw;
    }
    return {};
}

QDateTime MainWindow::createTimeForTaskId(const QString &taskId) const
{
    if (m_tasks.contains(taskId)) {
        return m_tasks.value(taskId).createTime;
    }
    if (m_results.contains(taskId)) {
        return m_results.value(taskId).createTime;
    }
    return {};
}

bool MainWindow::startResultDownloadForTask(const TaskModels::TaskDetail &task, const QString &reason)
{
    if (m_downloadInFlightTaskIds.contains(task.taskId)) {
        appendDiagnostic(QStringLiteral("Download already in progress for task %1.").arg(task.taskId));
        return true;
    }
    if (task.downloadUrl.isEmpty()) {
        const QString message = QStringLiteral("Task %1 has no download URL yet.").arg(task.taskId);
        appendDiagnostic(message);
        showUserNotice(message);
        return false;
    }

    QString directory;
    if (!ensureDownloadDirectory(directory)) {
        return false;
    }

    const QString localPath = QDir(directory).filePath(taskVideoFileName(task.taskId));
    m_downloadInFlightTaskIds.insert(task.taskId);
    appendDiagnostic(QStringLiteral("Downloading task %1 to %2 (%3).").arg(task.taskId, localPath, reason));
    showUserNotice(QStringLiteral("Downloading video: %1").arg(task.taskId));
    m_apiClient.downloadResult(task.taskId, QUrl(task.downloadUrl), localPath, QString::fromLatin1(kDownloadPurposeUser));
    return true;
}

bool MainWindow::startResultDownloadForResult(const TaskModels::ResultItem &result, const QString &reason)
{
    if (m_downloadInFlightTaskIds.contains(result.taskId)) {
        appendDiagnostic(QStringLiteral("Download already in progress for result %1.").arg(result.taskId));
        return true;
    }
    if (result.downloadUrl.isEmpty()) {
        const QString message = QStringLiteral("Result %1 has no download URL.").arg(result.taskId);
        appendDiagnostic(message);
        appendChatMessage(QStringLiteral("System"), message);
        showUserNotice(message);
        return false;
    }

    QString directory;
    if (!ensureDownloadDirectory(directory)) {
        return false;
    }

    const QString localPath = QDir(directory).filePath(taskVideoFileName(result.taskId));
    m_downloadInFlightTaskIds.insert(result.taskId);
    appendDiagnostic(QStringLiteral("Downloading result %1 to %2 (%3).").arg(result.taskId, localPath, reason));
    showUserNotice(QStringLiteral("Downloading video: %1").arg(result.taskId));
    m_apiClient.downloadResult(result.taskId, QUrl(result.downloadUrl), localPath, QString::fromLatin1(kDownloadPurposeUser));
    return true;
}

TaskModels::TaskDetail MainWindow::summaryToDetail(const TaskModels::TaskSummary &task) const
{
    TaskModels::TaskDetail detail;
    detail.taskId = task.taskId;
    detail.clientRequestId = task.clientRequestId;
    detail.mode = task.mode;
    detail.status = task.status;
    detail.prompt = task.prompt;
    detail.size = task.size;
    detail.outputPath = task.outputPath;
    detail.inputImagePath = task.inputImagePath;
    detail.errorMessage = task.errorMessage;
    detail.logPath = task.logPath;
    detail.createTimeRaw = task.createTimeRaw;
    detail.updateTimeRaw = task.updateTimeRaw;
    detail.createTime = task.createTime;
    detail.updateTime = task.updateTime;
    detail.outputExists = false;
    if (m_tasks.contains(task.taskId)) {
        const TaskModels::TaskDetail existing = m_tasks.value(task.taskId);
        detail.outputExists = existing.outputExists;
        detail.statusMessage = existing.statusMessage;
        detail.progressCurrent = existing.progressCurrent;
        detail.progressTotal = existing.progressTotal;
        detail.progressPercent = existing.progressPercent;
        detail.downloadUrl = existing.downloadUrl;
        if (detail.mode.isEmpty()) {
            detail.mode = existing.mode;
        }
        if (detail.size.isEmpty()) {
            detail.size = existing.size;
        }
        if (detail.inputImagePath.isEmpty()) {
            detail.inputImagePath = existing.inputImagePath;
        }
        detail.inputImageExists = existing.inputImageExists;
    }
    return detail;
}

QString MainWindow::formatTimestamp(const QDateTime &dateTime, const QString &fallback) const
{
    if (dateTime.isValid()) {
        return dateTime.toLocalTime().toString(QStringLiteral("yyyy-MM-dd HH:mm:ss"));
    }
    return fallback;
}
