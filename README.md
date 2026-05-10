# Korea Gas App for Home Assistant

Korea Gas App을 Home Assistant에서 사용할 수 있게 하는 커스텀 통합입니다.

가스앱 SMS 본인인증으로 로그인하고, 등록된 가스 계약의 청구금액과 검침 정보를 센서로 가져옵니다. 매일 오전 8시에 데이터를 갱신하며, 자가검침 기간이 되면 자동으로 자가검침을 제출합니다.

## 기능

- SMS 본인인증 기반 config flow
- 여러 가스 계정 동시 등록 지원 (계정별 별도 기기로 분리)
- 가스 계약 자동 조회 (여러 계약이 있으면 선택)
- 당월 청구금액 센서 (요금 세부 내역 속성 포함)
- 연간 청구 이력 센서 (청구연월별 사용량·청구금액 속성)
- 자가검침 이력 센서 (**자가검침 등록 계정에만 생성**)
- 자가검침 제출 결과 바이너리 센서 (**자가검침 등록 계정에만 생성**, 실패 이유 속성 포함)
- 자가검침을 나중에 신청하면 관련 센서 자동 활성화
- 매일 오전 8시 자동 데이터 갱신
- 자가검침 기간(periodStart 다음 날) 오전 8시에 자동 자가검침 제출
- 검침값 올림/내림 옵션
- 서비스 호출을 통한 수동 자가검침 제출

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
5. 자가검침 관련 설정을 입력합니다.
   - 가스미터 현재값 엔티티 — 자동 제출에 사용할 수치 엔티티
   - 검침값 반올림 방법 — 올림(ceil) 또는 내림(floor)

주민등록번호는 전체를 입력하지 않습니다. 앞 6자리와 하이픈 뒤 첫 자리만 입력합니다.

```text
950301-1
```

여러 계정을 추가하려면 통합 추가를 반복합니다. 각 계정은 별도의 기기로 분리됩니다.

## 생성되는 엔티티

엔티티 ID에는 사용계약번호 또는 고객번호가 붙습니다.

계약번호가 `1111111`인 경우:

| 엔티티 | 설명 | 조건 |
| --- | --- | --- |
| `sensor.current_bill_charge_1111111` | 당월 청구금액 | 항상 |
| `sensor.annual_bill_charge_1111111` | 연간 청구 이력 (최신 청구금액) | 항상 |
| `sensor.indication_history_1111111` | 자가검침 이력 (최근 검침일) | 자가검침 등록 계정만 |
| `binary_sensor.gas_meter_submission_result_1111111` | 자가검침 제출 결과 | 자가검침 등록 계정만 |

### sensor.current_bill_charge_1111111 속성

| 속성 | 설명 |
| --- | --- |
| `title` | 청구 제목 (예: 4월 총 청구 요금) |
| `status` | 납부 상태 |
| `payable` | 납부 가능 여부 |
| `basic_charge_krw` | 기본요금 |
| `usage_charge_krw` | 사용요금 |
| `vat_krw` | 부가세 |
| `discount_krw` | 할인금액 |
| `truncation_krw` | 절사금액 |
| `unpaid_krw` | 미납 소계 |
| `usage_period` | 사용 기간 |
| `due_date` | 납부 마감일 |
| `this_month_indicator_m3` | 당월지침 m³ |
| `last_month_indicator_m3` | 전월지침 m³ |
| `monthly_usage_m3` | 당월사용량 m³ |
| `correction_factor` | 보정 계수 |
| `correction_usage_m3` | 보정량 m³ |
| `avg_calorific_mj_m3` | 평균열량 MJ/m³ |
| `used_calorific_mj` | 사용열량 MJ |
| `meter_id` | 계량기 번호 |
| `reading_day` | 검침일 |
| `reading_method` | 검침방법 |
| `prev_month_usage` | 전월 사용량 비교 |
| `prev_year_usage` | 전년 동월 사용량 비교 |
| `discount_type` | 할인종류 |

### sensor.annual_bill_charge_1111111 속성

| 속성 | 설명 |
| --- | --- |
| `monthly_usage_m3` | `{"YYYY-MM": 사용량}` 딕셔너리 |
| `monthly_charge_krw` | `{"YYYY-MM": 청구금액}` 딕셔너리 |

### sensor.indication_history_1111111 속성

| 속성 | 설명 |
| --- | --- |
| `history` | 검침 이력 리스트 (검침일, 청구연월, 지침값 m³, 검침방법) |

### binary_sensor.gas_meter_submission_result_1111111

자가검침 제출 결과를 나타냅니다.

| 상태 | 의미 |
| --- | --- |
| `on` | 마지막 자가검침 제출 성공 |
| `off` | 마지막 자가검침 제출 실패, 또는 아직 제출한 적 없음 |

속성:

| 속성 | 설명 | 성공 시 | 실패 시 |
| --- | --- | --- | --- |
| `last_attempt_at` | 마지막 시도 일시 (ISO 형식) | ✔ | ✔ |
| `reading` | 제출한 검침값 m³ | ✔ | ✔ (값이 있을 때) |
| `result_message` | 성공 메시지 | ✔ | — |
| `failure_reason` | 실패 이유 | — | ✔ |
| `source` | 제출 출처 (`auto` 또는 `manual`) | ✔ | ✔ |

HA를 재시작해도 마지막 제출 결과가 유지됩니다.

## 업데이트 스케줄

데이터 갱신은 매일 **오전 8시**에 한 번 실행됩니다. 조회 주기는 설정할 수 없으며 고정입니다.

## 자동 자가검침 제출

자가검침이 등록된 계정은 가스앱 API에서 받아온 `periodStart`(검침 기간 시작일)의 **다음 날 오전 8시**에 자동으로 자가검침을 제출합니다.

제출 결과는 `binary_sensor.gas_meter_submission_result_*`에 즉시 반영됩니다.

제출이 실행되는 조건:

1. 자가검침 등록 계정일 것
2. 오늘 날짜가 `periodStart + 1일`일 것
3. 선택한 엔티티의 상태값이 유효한 숫자일 것
4. 값이 최근 검침값 이상이고, 최근 검침값 + 500 이하일 것

위 조건을 만족하지 못하면 자동 제출을 건너뛰고 실패 이유를 센서 속성에 기록합니다. `periodStart`를 API에서 가져오지 못한 경우에는 그 날 자동 제출 자체를 시도하지 않습니다.

### 검침값 반올림

엔티티 상태값이 소수점을 포함할 경우:

| 옵션 | 예 (446.4) | 예 (446.7) |
| --- | --- | --- |
| 올림 (ceil) | 447 | 447 |
| 내림 (floor) | 446 | 446 |

## 옵션

통합 옵션(**설정 > 기기 및 서비스 > Korea Gas App > 설정**)에서 변경할 수 있는 항목:

| 옵션 | 설명 |
| --- | --- |
| 가스미터 현재값 엔티티 | 자동 자가검침에 사용할 수치 엔티티 |
| 검침값 반올림 방법 | 올림(ceil) 또는 내림(floor) |

## 수동 자가검침 서비스

자동 제출에 실패하거나 직접 제출하고 싶을 때 사용합니다.  
성공하면 `binary_sensor.gas_meter_submission_result_*`가 `on`으로 변경됩니다.

```yaml
service: korea_gasapp.submit_meter_reading
data:
  reading: 5708
```

여러 계정이 등록된 경우 `account`를 함께 전달합니다.

```yaml
service: korea_gasapp.submit_meter_reading
data:
  account: "우리집"
  reading: 5708
```

`account`에는 다음 중 하나를 사용할 수 있습니다.

- 통합 항목 제목, 예: `우리집`
- 사용계약번호, 예: `1111111`
- 고객번호
- 화면에 보이는 기기명, 예: `Gas account 1111111`

수동 서비스 호출도 최대 범위(최근 검침값 + 500) 검사를 통과해야 제출됩니다.

## 자가검침 센서 자동 활성화

자가검침을 신청하지 않은 계정은 처음에 `indication_history` 센서와 `gas_meter_submission_result` 바이너리 센서가 생성되지 않습니다.

나중에 가스앱에서 자가검침을 신청하면 다음 날 오전 8시 갱신 시점에 두 엔티티가 자동으로 생성되며, 자동 자가검침 제출도 활성화됩니다.

## 개인정보 및 보안

- SMS 본인인증에 입력한 이름, 휴대폰 번호, 주민등록번호 앞부분, 인증번호는 설정 과정에서만 사용하며 config entry에 저장하지 않습니다.
- 발급된 가스앱 세션 토큰과 계약 정보는 Home Assistant 설정 저장소에 저장됩니다.

## 참고 사항

- 이 통합은 공식 가스앱 API 문서를 기반으로 한 것이 아닙니다.
- 가스앱 내부 API가 변경되면 로그인, 센서 조회, 자가검침 제출이 실패할 수 있습니다.

## Version History

- 2026/05/10 V1.0.0 Initial Release
- 2026/05/10 V1.0.1 검침 변화 최대값 추가
- 2026/05/11 V1.1.0
  - 센서 전면 개편: 당월 청구금액, 연간 청구 이력, 자가검침 이력 센서 추가
  - 여러 계정 등록 시 계정별 별도 기기로 분리
  - 자가검침 등록 계정에만 관련 센서 생성
  - 자가검침 미등록 계정이 나중에 신청하면 센서 자동 활성화
  - periodStart 기반 자동 제출 날짜 산출
  - 검침값 올림/내림 옵션 추가
- 2026/05/11 V1.2.0
  - 데이터 갱신 주기를 매일 오전 8시 고정으로 변경
  - 자가검침 자동 제출을 오전 8시 갱신과 통합
  - 옵션에서 조회 주기, 자가검침일, 자가검침 시간, 검침 변화 최대값 제거
  - periodStart 없을 때 자동 제출 건너뜀
- 2026/05/11 V1.3.0
  - 자가검침 가능 여부 바이너리 센서 제거
  - 자가검침 제출 결과 바이너리 센서 추가 (성공/실패, 실패 이유, 제출값, 출처 속성)
  - HA 재시작 후에도 마지막 제출 결과 유지 (RestoreEntity)
  - 수동 서비스 제출 성공 시에도 결과 센서 업데이트
