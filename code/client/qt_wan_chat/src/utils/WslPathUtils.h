#pragma once

#include <QString>

namespace WslPathUtils {

bool linuxPathToWindowsShare(const QString &linuxPath, const QString &distro, QString &windowsPath, QString &error);
bool outputDirectoryForLinuxFile(const QString &linuxFilePath, const QString &distro, QString &directoryPath, QString &error);

} // namespace WslPathUtils

