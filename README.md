# Korea Gas App for Home Assistant

가스앱의 사용량/청구/자가검침 정보를 Home Assistant에서 사용할 수 있게 하는 커스텀 통합입니다.

이 통합은 가스앱의 모바일 API를 사용해 계정 인증, 계약 조회, 센서 생성, 자가검침 제출을 처리합니다.

## 주요 기능

- Home Assistant UI에서 SMS 본인인증으로 통합 추가
- 최근 청구금액 센서 제공
- 최근 검침값 센서 제공
- 자가검침 가능 여부 바이너리 센서 제공
- 지정한 검침일/시간에 가스미터 현재값 엔티티를 읽어 자동 자가검침 제출
- 서비스 호출로 수동 자가검침 제출
- 사진 없이 숫자 검침값만 제출

## 설치

`custom_components/korea_gasapp` 폴더를 Home Assistant 설정 경로의 `custom_components` 아래에 복사합니다.

예:

```text
config/
  custom_components/
    korea_gasapp/
      __init__.py
      manifest.json
      ...
```

복사 후 Home Assistant를 재시작하세요.

## 통합 추가

1. Home Assistant에서 **설정 > 기기 및 서비스 > 통합 추가**로 이동합니다.
2. **Korea Gas App**을 선택합니다.
3. 가스앱 본인인증 정보를 입력합니다.
   - 이름
   - 휴대폰 번호
   - 주민등록번호 앞부분, 예: `950301-1`
   - 통신사
4. 문자로 받은 인증번호를 입력합니다.
5. 검침일, 검침 시간, 가스미터 현재값 엔티티를 선택합니다.

주민등록번호는 전체를 입력하지 않습니다. 앞 6자리와 하이픈 뒤 첫 자리만 입력합니다.

## 생성되는 엔티티

### 센서

| 엔티티 | 설명 |
| --- | --- |
| `sensor.latest_bill_charge` | 최근 청구금액 |
| `sensor.last_meter_reading` | 최근 검침값 |

`sensor.latest_bill_charge` 속성:

- `latest_bill_month`
- `latest_bill_usage_m3`

`sensor.last_meter_reading` 속성:

- `latest_indication_date`

### 바이너리 센서

| 엔티티 | 설명 |
| --- | --- |
| `binary_sensor.self_meter_reading_available` | 자가검침 가능 여부 |

이미 Home Assistant에 같은 이름의 엔티티가 있으면 실제 entity_id 뒤에 `_2`, `_3` 등이 붙을 수 있습니다.

## 옵션

통합 옵션에서 다음 값을 변경할 수 있습니다.

- 조회 주기: 기본 `60`분
- 자가검침일
- 자가검침 시간
- 가스미터 현재값 엔티티

자동 자가검침은 설정한 날짜와 시간에 선택한 엔티티의 상태값을 정수로 변환해 제출합니다.

## 수동 자가검침 서비스

서비스:

```yaml
korea_gasapp.submit_meter_reading
```

단일 계정이면 `reading`만 전달하면 됩니다.

```yaml
service: korea_gasapp.submit_meter_reading
data:
  reading: 5708
```

여러 계정을 등록한 경우에는 `account`를 함께 전달할 수 있습니다.

`account`에는 다음 값 중 하나를 사용할 수 있습니다.

- 통합 항목 제목, 예: `우리집`
- 사용계약번호, 예: `1613542`
- 고객번호
- 화면에 보이는 기기명, 예: `Gas account 1613542`

```yaml
service: korea_gasapp.submit_meter_reading
data:
  account: "우리집"
  reading: 5708
```

## 자동화 예시

통합 자체에 자동 제출 기능이 있지만, 직접 자동화를 만들 수도 있습니다.

```yaml
alias: Submit gas meter reading
trigger:
  - platform: time
    at: "08:00:00"
condition:
  - condition: template
    value_template: "{{ now().day == 5 }}"
action:
  - service: korea_gasapp.submit_meter_reading
    data:
      reading: "{{ states('input_number.gas_meter_reading') | int }}"
mode: single
```

## 참고 사항

- 이 통합은 공식 가스앱 API 문서를 기반으로 한 것이 아닙니다.
- 가스앱의 내부 API가 변경되면 로그인이 실패하거나 센서 값이 비어 있을 수 있습니다.
- SMS 본인인증에 입력한 이름, 휴대폰 번호, 주민등록번호 앞부분, 인증번호는 설정 과정에서만 사용되며 config entry에 저장하지 않습니다.
- 발급된 세션 토큰과 계약 정보는 Home Assistant 설정 저장소에 저장됩니다. Home Assistant 설정 파일과 백업은 안전하게 보관하세요.

## 개발/검증 도구

`tools/` 폴더에는 mitmproxy 캡처 분석과 로컬 검증에 사용한 보조 스크립트가 포함되어 있습니다. 일반 사용에는 필요하지 않습니다.
