#!/usr/bin/env bash
# Source this script so the environment and directory change persist.
if [[ ${BASH_SOURCE[0]} == "$0" ]]; then
    printf '현재 터미널에 적용하려면 source로 실행하세요:\n  source %q\n' "$0" >&2
    exit 1
fi

_boot_time_setup_env() {
    local build_dir
    build_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../build" && pwd -P) || return 1
    if [[ ! -r "$build_dir/conf/setenv" ]]; then
        printf '환경 설정 파일을 찾을 수 없습니다: %s/conf/setenv\n' "$build_dir" >&2
        return 1
    fi
    cd -- "$build_dir" || return 1
    # setenv also sets the UTF-8 locale and the open-file soft limit to 4096.
    source conf/setenv || return 1
    export MACHINE="${MACHINE:-j7200-evm}"
    command -v bitbake >/dev/null || {
        printf '환경 설정 후에도 bitbake를 찾을 수 없습니다.\n' >&2
        return 1
    }
    printf 'BitBake 환경 활성화 완료\n빌드 디렉터리: %s\nMACHINE: %s\n' "$PWD" "$MACHINE"
}

if ! _boot_time_setup_env; then
    unset -f _boot_time_setup_env
    return 1
fi
unset -f _boot_time_setup_env
