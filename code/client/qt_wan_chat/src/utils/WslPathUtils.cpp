#include "utils/WslPathUtils.h"

#include <QStringList>

namespace WslPathUtils {

bool linuxPathToWindowsShare(const QString &linuxPath, const QString &distro, QString &windowsPath, QString &error)
{
    const QString trimmedPath = linuxPath.trimmed();
    const QString trimmedDistro = distro.trimmed();

    if (trimmedDistro.isEmpty()) {
        error = QStringLiteral("WSL distro is empty.");
        return false;
    }
    if (!trimmedPath.startsWith(QLatin1Char('/'))) {
        error = QStringLiteral("WSL path must start with '/': %1").arg(trimmedPath);
        return false;
    }

    const QStringList parts = trimmedPath.split(QLatin1Char('/'), Qt::SkipEmptyParts);
    if (parts.isEmpty()) {
        error = QStringLiteral("WSL path is missing path segments: %1").arg(trimmedPath);
        return false;
    }

    windowsPath = QStringLiteral("\\\\wsl$\\%1\\%2")
                      .arg(trimmedDistro, parts.join(QLatin1Char('\\')));
    return true;
}

bool outputDirectoryForLinuxFile(const QString &linuxFilePath, const QString &distro, QString &directoryPath, QString &error)
{
    const QString trimmedPath = linuxFilePath.trimmed();
    if (trimmedPath.isEmpty()) {
        error = QStringLiteral("Output path is empty.");
        return false;
    }

    const int separatorIndex = trimmedPath.lastIndexOf(QLatin1Char('/'));
    if (separatorIndex <= 0) {
        error = QStringLiteral("Output path does not contain a parent directory: %1").arg(trimmedPath);
        return false;
    }

    const QString parentLinuxPath = trimmedPath.left(separatorIndex);
    return linuxPathToWindowsShare(parentLinuxPath, distro, directoryPath, error);
}

} // namespace WslPathUtils

