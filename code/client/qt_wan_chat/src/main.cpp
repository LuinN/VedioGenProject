#include "ApiClient.h"
#include "MainWindow.h"
#include "models/TaskModels.h"

#include <QApplication>
#include <QCommandLineOption>
#include <QCommandLineParser>
#include <QTextStream>
#include <QTimer>
#include <QtGlobal>

#include <limits>

namespace {

constexpr int kDefaultSmokeTimeoutMs = 60 * 60 * 1000;

} // namespace

int main(int argc, char *argv[])
{
    QApplication app(argc, argv);
    app.setOrganizationName(QStringLiteral("VideoGenProject"));
    app.setApplicationName(QStringLiteral("qt_wan_chat"));
    app.setApplicationDisplayName(QStringLiteral("Wan Chat Client MVP"));

    qRegisterMetaType<RequestKind>("RequestKind");
    qRegisterMetaType<RequestFailure>("RequestFailure");
    qRegisterMetaType<ResultDownload>("ResultDownload");
    qRegisterMetaType<TaskModels::HealthResponse>("TaskModels::HealthResponse");
    qRegisterMetaType<TaskModels::TaskSummary>("TaskModels::TaskSummary");
    qRegisterMetaType<TaskModels::TaskDetail>("TaskModels::TaskDetail");
    qRegisterMetaType<TaskModels::TaskListResponse>("TaskModels::TaskListResponse");
    qRegisterMetaType<TaskModels::ResultItem>("TaskModels::ResultItem");
    qRegisterMetaType<TaskModels::ResultListResponse>("TaskModels::ResultListResponse");

    QCommandLineParser parser;
    parser.setApplicationDescription(QStringLiteral("Windows Qt client for Wan local service."));
    parser.addHelpOption();
    QCommandLineOption smokePromptOption(
        QStringList{QStringLiteral("smoke-prompt")},
        QStringLiteral("Run a smoke test by submitting the provided prompt and exit when the task reaches a terminal state."),
        QStringLiteral("prompt"));
    QCommandLineOption smokeTaskIdOption(
        QStringList{QStringLiteral("smoke-task-id")},
        QStringLiteral("Run a smoke test by polling an existing task id without creating a new task."),
        QStringLiteral("task_id"));
    QCommandLineOption smokeTimeoutOption(
        QStringList{QStringLiteral("smoke-timeout-ms")},
        QStringLiteral("Maximum smoke-test wait time in milliseconds."),
        QStringLiteral("milliseconds"),
        QString::number(kDefaultSmokeTimeoutMs));
    QCommandLineOption smokeDownloadDirOption(
        QStringList{QStringLiteral("smoke-download-dir")},
        QStringLiteral("Download the smoke-test result into this local Windows directory before exiting successfully."),
        QStringLiteral("directory"));
    parser.addOption(smokePromptOption);
    parser.addOption(smokeTaskIdOption);
    parser.addOption(smokeTimeoutOption);
    parser.addOption(smokeDownloadDirOption);
    parser.process(app);

    const bool hasSmokePrompt = parser.isSet(smokePromptOption);
    const bool hasSmokeTaskId = parser.isSet(smokeTaskIdOption);
    if (hasSmokePrompt && hasSmokeTaskId) {
        QTextStream(stderr) << "--smoke-prompt and --smoke-task-id are mutually exclusive.\n";
        return 2;
    }

    int smokeTimeoutMs = kDefaultSmokeTimeoutMs;
    if (parser.isSet(smokeTimeoutOption)) {
        bool parsed = false;
        const qlonglong value = parser.value(smokeTimeoutOption).toLongLong(&parsed);
        if (!parsed || value <= 0 || value > std::numeric_limits<int>::max()) {
            QTextStream(stderr)
                << QStringLiteral("--smoke-timeout-ms must be a positive integer no larger than %1.\n")
                       .arg(std::numeric_limits<int>::max());
            return 2;
        }
        smokeTimeoutMs = static_cast<int>(value);
    }

    MainWindow window;
    const QString smokeDownloadDir = parser.value(smokeDownloadDirOption).trimmed();
    if (!smokeDownloadDir.isEmpty() && !hasSmokePrompt && !hasSmokeTaskId) {
        QString error;
        if (!window.setDownloadDirectory(smokeDownloadDir, &error)) {
            QTextStream(stderr) << error << Qt::endl;
            return 2;
        }
    }
    window.show();

    if (hasSmokePrompt || hasSmokeTaskId) {
        const QString prompt = parser.value(smokePromptOption).trimmed();
        const QString taskId = parser.value(smokeTaskIdOption).trimmed();
        QObject::connect(&window, &MainWindow::smokeTestFinished, &app, [&app](bool success, const QString &summary) {
            QTextStream stream(success ? stdout : stderr);
            stream << summary << Qt::endl;
            if (success) {
                app.exit(0);
                return;
            }
            app.exit(1);
        });
        QTimer::singleShot(0, &window, [prompt, taskId, smokeTimeoutMs, smokeDownloadDir, hasSmokePrompt, &window]() {
            if (hasSmokePrompt) {
                window.startSmokeTest(prompt, smokeTimeoutMs, smokeDownloadDir);
                return;
            }
            window.startTaskMonitorSmoke(taskId, smokeTimeoutMs, smokeDownloadDir);
        });
    }

    return app.exec();
}
