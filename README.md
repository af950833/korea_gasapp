# Korea Gas App for Home Assistant

Korea Gas App을 Home Assistant에서 사용할 수 있게 하는 커스텀 통합입니다.

가스앱 SMS 본인인증으로 로그인하고, 등록된 가스 계약의 최근 청구금액과 검침값을 센서로 가져옵니다. 설정한 날짜와 시간에는 Home Assistant 엔티티의 가스미터 값을 읽어 자가검침을 자동 제출할 수 있습니다.

## 기능

- SMS 본인인증 기반 config flow
- 가스 계약 자동 조회
- 최근 청구금액 센서
- 최근 검침값 센서
- 자가검침 가능 여부 바이너리 센서
- 지정한 날짜/시간에 자동 자가검침 제출
- 서비스 호출을 통한 수동 자가검침 제출
- 사진 없이 숫자 검침값만 제출

## 설치

### HACS

1. Home Assistant에서 **HACS > Integrations**로 이동합니다.
2. 우측 상단 메뉴에서 **Custom repositories**를 선택합니다.
3. 저장소 주소를 입력합니다.

   ```text
   https://github.com/af950833/korea_gasapp
   ```

4. Category는 **Integration**으로 선택합니다.
5. **Korea Gas App**을 검색해 설치합니다.
6. Home Assistant를 재시작합니다.

### 수동 설치

`custom_components/korea_gasapp` 폴더를 Home Assistant 설정 경로의 `custom_components` 아래에 복사합니다.

```text
config/
  custom_components/
    korea_gasapp/
      __init__.py
      manifest.json
      ...
```

복사 후 Home Assistant를 재시작합니다.

## 통합 추가

1. Home Assistant에서 **설정 > 기기 및 서비스 > 통합 추가**로 이동합니다.
2. **Korea Gas App**을 선택합니다.
3. 본인인증 정보를 입력합니다.
   - 이름
   - 휴대폰 번호
   - 주민등록번호 앞부분, 예: `950301-1`
   - 통신사
4. 문자로 받은 인증번호를 입력합니다.
5. 자가검침일, 자가검침 시간, 가스미터 현재값 엔티티를 선택합니다.
6. 검침 변화 최대값을 입력합니다. 기본값은 `500`입니다.

주민등록번호는 전체를 입력하지 않습니다. 앞 6자리와 하이픈 뒤 첫 자리만 입력합니다.

```text
950301-1
```

## 생성되는 엔티티

엔티티 ID에는 사용계약번호 또는 고객번호가 붙습니다.

계약번호가 `1111111`인 경우:

| 엔티티 | 설명 |
| --- | --- |
| `sensor.latest_bill_charge_1111111` | 최근 청구금액 |
| `sensor.last_meter_reading_1111111` | 최근 검침값 |
| `binary_sensor.self_meter_reading_available_1111111` | 자가검침 가능 여부 |

`sensor.latest_bill_charge_1111111` 속성:

- `latest_bill_month`
- `latest_bill_usage_m3`

`sensor.last_meter_reading_1111111` 속성:

- `latest_indication_date`

## 옵션

통합 옵션에서 다음 값을 변경할 수 있습니다.

- 조회 주기: 기본 `60`분
- 자가검침일
- 자가검침 시간
- 가스미터 현재값 엔티티
- 검침 변화 최대값: 기본 `500`

자동 자가검침은 설정한 날짜와 시간에 선택한 엔티티의 상태값을 정수로 변환해 제출합니다.
제출값은 최근 검침값 이상이고, 최근 검침값에 검침 변화 최대값을 더한 값 이하일 때만 제출됩니다.

예를 들어 최근 검침값이 `5707`이고 검침 변화 최대값이 `500`이면 `5707`부터 `6207`까지의 값만 제출됩니다.

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

수동 서비스 호출도 검침 변화 최대값 검사를 통과해야 제출됩니다.

`account`에는 다음 값 중 하나를 사용할 수 있습니다.

- 통합 항목 제목, 예: `우리집`
- 사용계약번호, 예: `1111111`
- 고객번호
- 화면에 보이는 기기명, 예: `Gas account 1111111`

```yaml
service: korea_gasapp.submit_meter_reading
data:
  account: "우리집"
  reading: 5708
```

## 자동화 예시

통합 자체에 자동 제출 기능이 있지만, Home Assistant 자동화에서 서비스를 직접 호출할 수도 있습니다.

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

## 개인정보 및 보안

- SMS 본인인증에 입력한 이름, 휴대폰 번호, 주민등록번호 앞부분, 인증번호는 설정 과정에서만 사용하며 config entry에 저장하지 않습니다.
- 발급된 가스앱 세션 토큰과 계약 정보는 Home Assistant 설정 저장소에 저장됩니다.

## 참고 사항

- 이 통합은 공식 가스앱 API 문서를 기반으로 한 것이 아닙니다.
- 가스앱 내부 API가 변경되면 로그인, 센서 조회, 자가검침 제출이 실패할 수 있습니다.

## Version History

- 2026/05/10 V1.0.0 Initial Release
- 2026/05/10 V1.0.1 검침 변화 최대값 추가
