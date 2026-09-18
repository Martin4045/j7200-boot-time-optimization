# J7200: HyperFlash 부트와 eMMC rootfs 구성

## 1. 최종 부팅 경로

이 변경은 부팅 경로를 다음과 같이 고정한다.

```text
Boot ROM
  -> HyperFlash 0x0000000: tiboot3.bin
  -> HyperFlash 0x0100000: tispl.bin
  -> HyperFlash 0x0300000: u-boot.img
  -> HyperFlash 0x0800000: Linux Image
  -> HyperFlash 0x2000000: k3-j7200-common-proc-board.dtb
  -> eMMC UDA partition 2: rootfs와 원격 프로세서 펌웨어
```

U-Boot의 `bootdelay`는 0초이며, `uEnv.txt`, extlinux, bootflow 탐색을 거치지 않는다. Linux `Image`와 DTB는 HyperFlash의 고정 슬롯에서 RAM으로 직접 복사한다.

원격 프로세서 펌웨어 세 개는 eMMC rootfs의 `/lib/firmware`에서 읽는다. 이 파일들은 실행 중인 rootfs와 함께 갱신되어야 하고 합계가 약 1 MiB이므로, 별도 raw HyperFlash 슬롯으로 분리하지 않았다.

## 2. HyperFlash 배치

| 데이터 | Flash 오프셋 | 예약 크기 | A72 매핑 주소 |
|---|---:|---:|---:|
| `tiboot3.bin` | `0x0000000` | 1 MiB | `0x500000000` |
| `tispl.bin` | `0x0100000` | 2 MiB | `0x500100000` |
| `u-boot.img` | `0x0300000` | 4 MiB | `0x500300000` |
| 환경 영역 | `0x0700000` | 256 KiB | `0x500700000` |
| Linux `Image` | `0x0800000` | 24 MiB | `0x500800000` |
| DTB | `0x2000000` | 256 KiB | `0x502000000` |

`Image`와 DTB는 `hbmc.rootfs` MTD 파티션 안에 있지만 파일시스템을 만들지 않고 raw 데이터로 기록한다. 이름이 `rootfs`인 것은 기존 DT 파티션 이름일 뿐이며, 실제 Linux rootfs는 eMMC partition 2에 남는다.

## 3. 소스 변경

U-Boot bbappend에 다음 패치가 추가되었다.

```text
recipes-bsp/u-boot/u-boot-ti-staging/0005-j7200-boot-kernel-from-hyperflash.patch
```

패치의 주요 변경은 다음과 같다.

- `CONFIG_BOOTDELAY=0`
- `CONFIG_BOOTCOMMAND="run bootcmd_hbmc_emmc"`
- eMMC partition 2의 PARTUUID로 kernel command line 생성
- eMMC rootfs에서 원격 프로세서 펌웨어 로드
- HyperFlash의 `Image`와 DTB를 RAM으로 직접 복사
- Linux 실행
- HyperFlash의 `tiboot3` MTD 크기를 DT와 같은 1 MiB로 수정

기존 `0003-j7200-restore-hbmc-dll-calibration.patch`는 A72 SPL의 HyperFlash calibration을 안정화한다. 이 패치도 계속 적용된다.

## 4. 빌드

사용자가 기존 방식으로 이미지를 빌드한다.

```bash
cd /mnt/mydisk/dasan/yocto-build/build
MACHINE=j7200-evm bitbake tisdk-default-image
```

이 문서를 작성하면서 BitBake 빌드는 실행하지 않았다.

## 5. SD 카드용 업데이트 묶음 생성

빌드가 끝난 뒤 레이어 루트에서 실행한다.

```bash
cd /mnt/mydisk/dasan/yocto-build/sources/meta-boot-time
./tools/create_hyperflash_update.py
```

`hyperflash-update/`에 다음 파일이 생성된다.

```text
hf-tiboot3.bin
hf-tispl.bin
hf-u-boot.img
hf-kernel-dtb.bin
flash-hyperflash.cmd
flash-hyperflash.scr
manifest.json
```

도구는 다음 조건이면 즉시 중단한다.

- 새 U-Boot initial environment에 `bootdelay=0`과 `bootcmd_hbmc_emmc`가 없음
- `Image`, DTB 또는 bootloader가 예약 슬롯보다 큼

따라서 0005 패치 적용 후 새로 빌드하지 않은 결과물을 실수로 기록할 수 없다. `manifest.json`에는 입력과 출력의 크기 및 SHA-256이 기록된다.

## 6. SD 카드에 복사

SD 카드의 첫 번째 FAT 파티션 루트에 `hyperflash-update/` 안의 파일을 모두 복사한다. 디렉터리째 복사하지 말고 파일들이 FAT 파티션 최상위에 오게 한다. Bootloader에는 `hf-` 접두사를 사용하므로 SD 카드 자체의 `tiboot3.bin`, `tispl.bin`, `u-boot.img`를 덮어쓰지 않는다.

현재 Linux DT에서 SD 컨트롤러를 비활성화했어도 이 작업에는 문제가 없다. 기록은 Linux가 아니라 U-Boot에서 수행한다.

## 7. HyperFlash 기록

1. 현재 eMMC 부트 모드를 유지한다.
2. 보드의 HyperFlash/OSPI mux가 HyperFlash를 선택하도록 설정한다.
3. SD 카드를 꽂고 부팅한다.
4. 현재 U-Boot의 2초 카운트다운 중 아무 키나 눌러 프롬프트에 진입한다.
5. 다음 두 명령만 실행한다.

```text
fatload mmc 1:1 ${scriptaddr} flash-hyperflash.scr
source ${scriptaddr}
```

스크립트는 다음 순서로 처리한다.

1. 잘못된 기존 512 KiB 정의 대신 1 MiB `hbmc.tiboot3` 레이아웃을 설정한다.
2. Linux `Image`와 DTB 묶음을 기록하고 byte compare로 검증한다.
3. `u-boot.img`, `tispl.bin`, `tiboot3.bin` 순서로 기록하고 각각 검증한다.
4. 가장 중요한 첫 단계 이미지인 `tiboot3.bin`을 마지막에 기록한다.

마지막 출력이 다음과 같아야 한다.

```text
HyperFlash update completed successfully
```

중간에 `ERROR:`가 나오거나 compare가 실패하면 전원을 끄거나 부트 모드를 바꾸지 말고 해당 로그를 확인한다.

## 8. HyperFlash 부팅 전환과 확인

보드 전원을 끈 뒤 부트 모드 스위치를 HyperFlash primary boot로 바꾸고 다시 켠다. 정상 로그에는 다음 항목이 나타난다.

```text
Trying to boot from NOR
Loading Linux Image and DTB from HyperFlash
```

Linux 로그인 후 rootfs가 eMMC인지 확인한다.

```bash
findmnt -n -o SOURCE /
cat /proc/cmdline
```

기대 결과는 다음과 같다.

```text
/dev/mmcblk0p2
```

`/proc/cmdline`에는 eMMC partition 2의 `PARTUUID`가 `root=` 값으로 들어 있어야 한다.

## 9. 복구 방법

HyperFlash 부팅에 실패하면 부트 모드를 다시 eMMC로 바꾼다. eMMC의 bootloader와 rootfs는 이 작업에서 지우지 않으므로 기존 상태로 부팅할 수 있다.

새 U-Boot는 `bootdelay=0`이지만, `Image` 또는 DTB가 잘못되어 `booti`가 실패하면 U-Boot 프롬프트로 돌아온다. 수동으로 기존 eMMC 커널을 부팅하려면 다음 명령을 사용한다.

```text
setenv boot mmc
setenv mmcdev 0
setenv bootpart 0:2
run bootcmd_ti_mmc
```

## 10. 성능 판단 기준

기존 eMMC 측정에서는 `Image` 22,325,760바이트 읽기가 약 73 ms였다. 따라서 저장 매체를 HyperFlash로 바꾼 것만으로 더 빨라진다고 단정할 수 없다. 이번 구성에서 가장 큰 확정 절감은 2초의 U-Boot 대기와 일반 bootflow 탐색 제거다.

전환 후 기존 UART 측정 스크립트로 10회 측정하여 다음 두 값을 비교한다.

- Bootloader 구간 평균과 편차
- `Loading Linux Image and DTB from HyperFlash`부터 `Booting Linux`까지의 시간

HyperFlash 복사 시간이 eMMC의 기존 73 ms보다 길면, 최종 최저 부팅 시간은 같은 전용 boot command를 유지하면서 kernel/DTB만 eMMC raw 또는 ext4에서 읽는 구성이 더 빠를 수 있다.
