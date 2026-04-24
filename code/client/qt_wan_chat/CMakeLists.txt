cmake_minimum_required(VERSION 3.21)

project(qt_wan_chat LANGUAGES CXX)

set(CMAKE_AUTOMOC ON)
set(CMAKE_AUTOUIC OFF)
set(CMAKE_AUTORCC OFF)

find_package(Qt6 REQUIRED COMPONENTS Multimedia Network Widgets)

add_executable(qt_wan_chat
    src/main.cpp
    src/ApiClient.cpp
    src/ApiClient.h
    src/MainWindow.cpp
    src/MainWindow.h
    src/models/TaskModels.h
    src/utils/WslPathUtils.cpp
    src/utils/WslPathUtils.h
)

target_compile_features(qt_wan_chat PRIVATE cxx_std_17)

target_link_libraries(qt_wan_chat
    PRIVATE
        Qt6::Multimedia
        Qt6::Network
        Qt6::Widgets
)

target_include_directories(qt_wan_chat PRIVATE src)

if(WIN32)
    get_target_property(QT_QMAKE_EXECUTABLE Qt6::qmake IMPORTED_LOCATION)
    if(NOT QT_QMAKE_EXECUTABLE)
        message(FATAL_ERROR "Qt6::qmake target was not found; cannot locate windeployqt.")
    endif()

    get_filename_component(QT_BIN_DIR "${QT_QMAKE_EXECUTABLE}" DIRECTORY)
    find_program(WINDEPLOYQT_EXECUTABLE
        NAMES windeployqt.exe windeployqt
        HINTS "${QT_BIN_DIR}"
        REQUIRED
    )
    find_program(POWERSHELL_EXECUTABLE
        NAMES pwsh.exe powershell.exe
        PATHS
            "$ENV{ProgramFiles}/PowerShell/7"
            "$ENV{SystemRoot}/System32/WindowsPowerShell/v1.0"
        REQUIRED
    )

    set(QT_WAN_CHAT_RELEASE_DIR "${CMAKE_CURRENT_SOURCE_DIR}/release")
    add_custom_command(
        TARGET qt_wan_chat
        POST_BUILD
        COMMAND
            "${POWERSHELL_EXECUTABLE}"
            -NoProfile
            -ExecutionPolicy Bypass
            -File "${CMAKE_CURRENT_SOURCE_DIR}/tools/package_windows.ps1"
            -ExecutablePath "$<TARGET_FILE:qt_wan_chat>"
            -ReleaseDir "${QT_WAN_CHAT_RELEASE_DIR}"
            -WinDeployQt "${WINDEPLOYQT_EXECUTABLE}"
        COMMENT "Packaging qt_wan_chat into ${QT_WAN_CHAT_RELEASE_DIR}"
        VERBATIM
    )
endif()
