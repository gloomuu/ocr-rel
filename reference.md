# 售电公司注册资料 AI 识别与校核系统——开发指导手册

## 1. 总体架构与系统交互流程

本项目涉及两个系统：**我方系统（售电注册平台）**与**第三方 AI 识别系统**。AI 系统负责对上传的附件进行 OCR 文字识别并返回结构化数据，**字段的匹配与业务规则校核完全由我方系统完成** 。

```
[用户提交审核] -> (我方系统:生成UUID并存入Redis) -> (调用AI系统接口)
                                                    |
[我方接收回调并校验] <- (AI系统回调结果) <- (AI系统通过UUID下载Base64文件)

```

### 1.1 核心对接流程

1. 
**触发时机**：用户在售电公司注册流程中填报信息、上传附件并提交审核时，系统自动触发 AI 识别流程 。


2. 
**凭证映射**：我方系统为每个需要识别的附件生成唯一 UUID，建立 `UUID -> fileId` 的映射关系并写入 Redis 。


3. 
**异步请求**：我方调用 AI 系统的请求接口，传入注册记录 ID（`registrationId`）和按类型分组的附件 UUID 列表 。


4. 
**物料下载**：AI 系统通过我方的文件下载接口，利用 UUID 异步下载文件的 Base64 编码 。


5. 
**结果回调**：AI 系统完成识别后，将结构化数据通过回调接口返回给我方 。


6. 
**匹配校核**：我方系统接收回调数据，将其与数据库/页面填报的字段进行匹配校验，并执行特定的业务准入规则 。



---

## 2. 接口定义与数据结构映射

代码开发智能体需严格按照以下契约实现接口的发送与接收逻辑。

### 2.1 提交 AI 识别请求（我方 $\rightarrow$ 贵方）

* 
**请求方式**：`POST` 


* 
**Content-Type**：`application/json` 


* 
**核心 Payload 结构** ：



```json
{
  "registrationId": "string (sale_company_registration.id)",
  "files": [
    {
      "type": "integer (1-11)",
      "name": "string (附件类型名称)",
      "files": [
        { "uuid": "string (临时文件UUID)", "personnel": "string (可选，人员姓名)" }
      ]
    }
  ]
}

```

### 2.2 附件文件下载接口（贵方 $\rightarrow$ 我方）

* 
**接口地址**：`/api/ai/file/download` 


* 
**请求方式**：`POST` 


* 
**Redis 校验逻辑** ：


* Key：`ai:file:uuid:{uuid}`
* Value：`fileId`（内部文件服务器 ID）


* 
**异常处理**：若 UUID 不存在或已过期，返回 `1001` 。


* 
**成功响应** ：`data.fileName` 和 `data.base64Content`。



### 2.3 AI 识别结果回调接口（贵方 $\rightarrow$ 我方）

* 
**接口地址**：`/api/ai/result/callback` 


* 
**请求方式**：`POST` 


* **数据接收规范**：
* 必须支持同一种 `type` 下包含多个 `detail` 元素（如多名从业人员、多个董监高信用材料） 。


* 针对包含 `personnel` 字段的类型（`type=5, 9, 10`），需原样接收以确保人员对齐 。





---

## 3. 核心业务校核逻辑与规则引擎

这是本手册的核心。智能体需在回调处理类（如 `AiCallbackService`）中，对 AI 返回的结构化文本与我方数据库表 `sale_company_registration` 进行全量或特定规则的核准。

### 3.1 基础证照与表字段映射核对表

当收到回调时，应执行以下字段的 **`String.equals()`** 或日期格式化对齐校验 ：

| 附件类型 (`type`) 

 | AI 回调字段 

 | 我方数据库字段 (`sale_company_registration`) 

 | 校核要求与业务说明 

 |
| --- | --- | --- | --- |
| <br>**1: 营业执照** 

 | <br>`unifiedSocialCreditCode`<br>

<br>`companyName`<br>

<br>`establishDate`<br>

<br>`registeredAddress`<br>

<br>`registerAuthority`<br>

<br>`approvalDate` 

 | <br>`credit_code`<br>

<br>`sale_company_name`<br>

<br>`establishing_date`<br>

<br>`industrial_register_place`<br>

<br>`industrial_register_office`<br>

<br>`approval_date` 

 | <br>**全相符校验**：OCR 识别出的各项工商要素必须与系统填报信息完全一致 。

 |
| <br>**2: 法人身份证** 

 | <br>`name`<br>

<br>`idCardNumber` 

 | <br>`legal_person_name`<br>

<br>`id_card` 

 | <br>**一致性校验**：必须与填报的法人姓名和证件号自动校验一致 。

 |
| <br>**3: 审计报告** 

 | <br>`companyName`<br>

<br>`accountingFirmName`<br>

<br>`reportCode`<br>

<br>`totalAssets` 

 | <br>`sale_company_name`<br>

<br>（表单辅助字段）<br>

<br>（表单辅助字段）<br>

<br>`total_assets` 

 | <br>**公司名校验**：报告中的售电公司名称需与填报一致 。

<br>

<br>**特殊数值换算（见 3.2）** 。

 |
| <br>**4: 验资报告** 

 | <br>`companyName`<br>

<br>`accountingFirmName`<br>

<br>`reportCode` 

 | `sale_company_name`<br>

<br>（表单辅助字段）<br>

<br>（表单辅助字段） | <br>**公司名校验**：报告中的公司名称、事务所名称及编码需一致 。

 |
| <br>**5: 从业人员身份证** 

 | <br>`name`<br>

<br>`idCardNumber` 

 | （`sale_company_personnel` 关联表） | <br>**多记录匹配**：依据 `personnel` 标识或身份证号，自动校验人员信息 。

 |
| <br>**6: 等级保护备案证明** 

 | <br>`systemLevel` 

 | <br>`safety_level` 

 | <br>**系统等级校验**：与系统填报的等保级别（如二级、三级）自动校验 。

<br>

<br>**双证交叉校验（见 3.3）** 。

 |
| <br>**7: 法人征信报告** 

 | <br>`name`<br>

<br>`idCardNumber` 

 | <br>`legal_person_name`<br>

<br>`id_card` 

 | <br>**主体一致性**：确认征信报告属于法人本人 。

 |
| <br>**8~11: 各类信用证明** 

 | <br>`executedPersonName`<br>

<br>`queryResult` 

 | （信用筛查关联表） | <br>**黑名单核准**：识别截图中的人名/企业名及结果，自动校验其失信状态 。

 |

---

### 3.2 硬性数量及数值判定准则（规则引擎核心）

智能体在解析完回调或表单提交时，必须硬编码或配置以下高内聚的判定逻辑：

规则 1：经营场所租赁期限自动校验 

* **触发点**：用户填报经营场所信息时。
* 
**判定逻辑**：$\text{租赁截至日期} - \text{租赁起始日期} \ge 1 \text{ 年}$（或 $365 \text{ 天}$），少于一年系统必须拦截并提示错误 。



规则 2：中高级职称人员数量自动判定 

* **触发点**：填报人员列表资质核验。
* **判定逻辑**：系统自动统计填报的人员列表中，持有中高级职称的人员总数：

$$\text{Count}(\text{职称} \in \{\text{中级}, \text{高级}\}) \ge 4$$


若少于 4 人，判定为不合规 。



规则 3：售电公司资产总额判定与单位换算 

* 
**数据换算处理**：AI 回调的审计报告（`type=3`）中的 `totalAssets` 单位为**元** 。我方数据库 `total_assets` 的存储单位为**万元** 。


* **计算公式**：

$$\text{total\_assets (万元)} = \text{Round}\left(\frac{\text{totalAssets (元)}}{10000}, 4\right)$$



开发实现注意：Java 必须使用 `BigDecimal` 进行除法，并设置 `RoundingMode.HALF_UP` 保留 4 位小数 。


* 
**资产准入门槛判定**：无论是通过审计报告填报还是直接填报，售电公司的资产总额数值**绝对不得少于 2000 万元人民币** 。



$$\text{存储值 } total\_assets \ge 2000.0000$$



---

### 3.3 跨附件强一致性交叉校验（Soft-Wares 匹配规则）

根据功能需求第 6 项，针对技术支持系统的**软件著作证书**（`type=6` 衍生/辅助件）与**等保备案证明**（`type=6`）存在特殊的跨文件交叉校验 ：

```
[软件著作证书] -> 提取 著作权人 (如: 河南省泛物网络科技有限公司)
                                       | (必须完全一致)
[等保备案证明] -> 提取 单位名称 (如: 河南省泛物网络科技有限公司)

```

* 
**逻辑要求**：智能体需在回调处理中拦截 `type=6` 的识别流，提取软件著作证书的“著作权人”与等保备案证明的“单位名称”，执行强一致性对比，**两者名称不一致时判定为校验失败** 。



---

## 4. 智能体编程实现指导（伪代码）

请代码开发智能体根据以下伪代码逻辑结构进行具体工程落地：

```java
/**
 * AI识别结果回调核心处理服务
 */
@Service
public class AiCallbackServiceImpl implements AiCallbackService {

    @Autowired
    private SaleCompanyRegistrationRepository registrationRepo;

    @Transactional
    public CallbackResponse handleAiCallback(AiCallbackRequest request) {
        String registrationId = request.getRegistrationId();
        // 1. 获取本地填报的申请单快照数据
        SaleCompanyRegistration entity = registrationRepo.findById(registrationId)
            .orElseThrow(() -> new BusinessException("未找到对应的注册记录: " + registrationId));

        List<ValidationResult> reportResults = new ArrayList<>();

        // 2. 迭代处理每一种附件类型的识别数据
        for (TypeResult result : request.getResults()) {
            switch (result.getType()) {
                case 1: // 营业执照
                    validateBusinessLicense(result.getDetail(), entity, reportResults);
                    break;
                case 2: // 法人身份证
                    validateLegalPersonIdCard(result.getDetail(), entity, reportResults);
                    break;
                case 3: // 审计报告
                    validateAuditReportAndConvert(result.getDetail(), entity, reportResults);
                    break;
                case 6: // 软著与等保交叉校验
                    validateSecurityAndCopyright(result.getDetail(), entity, reportResults);
                    break;
                // 其他类型按需扩展...
            }
        }

        // 3. 执行系统级强硬性指标判定
        executeHardSystemRules(entity, reportResults);

        // 4. 将比对结果和高亮错误信息持久化或推送到前端展示
        saveAndPushResults(registrationId, reportResults);

        return CallbackResponse.success();
    }

    private void validateAuditReportAndConvert(List<AuditDetail> details, SaleCompanyRegistration entity, List<ValidationResult> reports) {
        if (details == null || details.isEmpty()) return;
        AuditDetail aiDetail = details.get(0);
        
        // 核心逻辑：单位元转万元，四舍五入保留4位小数
        BigDecimal totalAssetsInYuan = BigDecimal.valueOf(aiDetail.getTotalAssets());
        BigDecimal totalAssetsInWanYuan = totalAssetsInYuan.divide(new BigDecimal("10000"), 4, RoundingMode.HALF_UP);
        
        // 更新或比对数据库中的数值
        entity.setTotalAssets(totalAssetsWanYuan);
        
        // 校验资产是否少于2000万元
        if (totalAssetsWanYuan.compareTo(new BigDecimal("2000.0000")) < 0) {
            reports.add(new ValidationResult("total_assets", "资产总额不合规", "售电公司资产总额不得少于2000万元人民币"));
        }
    }

    private void executeHardSystemRules(SaleCompanyRegistration entity, List<ValidationResult> reports) {
        // 校验租赁期限
        long leaseDays = ChronoUnit.DAYS.between(entity.getLeaseStartDate(), entity.getLeaseEndDate());
        if (leaseDays < 365) {
            reports.add(new ValidationResult("lease_period", "不合规", "经营场所租赁期限不得少于一年"));
        }

        // 校验中高级职称人数 (假设关联表查询结果为 count)
        int titleCount = registrationRepo.countMedHighTitlePersonnel(entity.getId());
        if (titleCount < 4) {
            reports.add(new ValidationResult("personnel_title_count", "不合规", "中高级职称人员数量不得少于4人"));
        }
    }
}

```

---

## 5. 交付与联调边界规范

1. 
**接口安全**：代码开发时需预留鉴权拦截器（Interceptor/Filter），支持 Token 鉴权（`Authorization: Bearer`）或 API Key 方案，具体视最终配置而定 。


2. 
**异常重试容错**：我方回调接口如遇非 `0` 异常响应，第三方将进行最多 3 次、间隔 30 秒的重试 。我方接口应确保**幂等性**设计，避免因网络抖动导致数据重复校验而产生脏数据。


3. 
**高精确度**：处理 `totalAssets` 等涉及多项货币格式化的字段时，绝不可采用 `float` 或 `double` 承接，必须全程以 `BigDecimal`（在数据库中表现为 `decimal(20,4)`）进行计算和判定 。