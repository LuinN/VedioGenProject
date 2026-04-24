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
