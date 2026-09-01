// Windows 上 release 模式不弹控制台窗口
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

fn main() {
    biodsh_desktop_lib::run();
}
