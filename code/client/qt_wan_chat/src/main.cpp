#include "ApiClient.h"
#include "MainWindow.h"
#include "models/TaskModels.h"

#include <QApplication>
#include <QCommandLineOption>
#include <QCommandLineParser>
#include <QTimer>
#include <QtGlobal>

int main(int argc, char *argv[])
{
    QApplication app(argc, argv);
    app.setApplicationName(QStringLiteral("qt_wan_chat"));
    app.setApplicationDisplayName(QStringLiteral("Wan Chat Client MVP"));

    qRegisterMetaType<RequestKind>("RequestKind");
    qRegisterMetaType<RequestFailure>("RequestFailure");
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
    parser.addOption(smokePromptOption);
    parser.process(app);

    MainWindow window;
    window.show();

    if (parser.isSet(smokePromptOption)) {
        const QString prompt = parser.value(smokePromptOption).trimmed();
        QObject::connect(&window, &MainWindow::smokeTestFinished, &app, [&app](bool success, const QString &summary) {
            if (success) {
                qInfo().noquote() << summary;
                app.exit(0);
                return;
            }
            qCritical().noquote() << summary;
            app.exit(1);
        });
        QTimer::singleShot(0, &window, [prompt, &window]() {
            window.startSmokeTest(prompt);
        });
    }

    return app.exec();
}
