# Gradual Rollout Plan - AI Processor Refactoring

## Executive Summary

แผนการ rollout แบบค่อยเป็นค่อยไปเพื่อลดความเสี่ยงในการนำ AI Processor ที่ refactor แล้วไปใช้งานจริง

---

## 1. Pre-Rollout Checklist

### 1.1 Staging Validation ✅
- [x] Staging deployment config ready
- [x] Docker Compose สำหรับ staging
- [x] Database initialization scripts
- [x] Environment variable configs

### 1.2 Testing Status ✅
- [x] Video Regression Tests: 17/17 passed (100%)
- [x] Stream Regression Tests: Created
- [x] Monitoring Dashboard Tests: 3/3 passed
- [x] Resume functionality: Implemented

### 1.3 Feature Flag Status ✅
| Feature | Flag | Default | Status |
|---------|------|---------|--------|
| Image Analyzer | `USE_REFACTORED_IMAGE_ANALYZER` | `false` | ✅ Ready |
| Video Processor | `USE_REFACTORED_VIDEO_PROCESSOR` | `false` | ✅ Ready |
| Stream Processor | `USE_REFACTORED_STREAM_PROCESSOR` | `false` | ✅ Ready |

---

## 2. Rollout Phases

### Phase 1: Image Analysis Only (Low Risk)
**Timeline:** Day 1-2  
**Traffic:** 10% → 50% → 100%

**Steps:**
1. Set `USE_REFACTORED_IMAGE_ANALYZER=true` on staging
2. Test with internal users for 24 hours
3. Deploy to production with 10% traffic
4. Monitor for 12 hours, increase to 50% if stable
5. Full rollout after 24 hours stable

**Rollback Trigger:**
- Error rate > 1%
- Response time > 5 seconds (baseline: 2s)
- User complaints

**How to Rollback:**
```bash
# Immediate rollback
set USE_REFACTORED_IMAGE_ANALYZER=false
```

---

### Phase 2: Video Upload Processing
**Timeline:** Day 3-7  
**Traffic:** 10% → 25% → 50% → 100%

**Prerequisites:**
- Phase 1 stable for 48 hours
- Video regression tests pass
- Resume functionality tested

**Steps:**
1. Set `USE_REFACTORED_VIDEO_PROCESSOR=true` on staging
2. Test video uploads of various sizes (10MB, 100MB, 500MB)
3. Deploy to production with 10% traffic
4. Monitor progress dashboard for 24 hours
5. Increase traffic gradually (25% → 50% → 100%)

**Metrics to Monitor:**
- Processing completion rate > 95%
- Average processing time vs baseline
- Database batch insert success rate
- MinIO upload success rate
- Resume functionality working

**Rollback Trigger:**
- Processing failure rate > 5%
- Average processing time > 120% of baseline
- Resume functionality failing

---

### Phase 3: Real-time Stream Processing
**Timeline:** Day 8-14  
**Traffic:** 5% → 10% → 25% → 100%

**Prerequisites:**
- Phase 2 stable for 72 hours
- Stream tests pass on staging
- Multi-camera testing complete

**Steps:**
1. Set `USE_REFACTORED_STREAM_PROCESSOR=true` on staging
2. Test with 2-3 cameras simultaneously
3. Deploy to production with 5% traffic (new cameras only)
4. Monitor for 48 hours
5. Gradually increase to 100%

**Special Considerations:**
- Stream processing affects real-time monitoring
- Lower initial traffic percentage (5%)
- Longer monitoring period (48 hours per stage)

---

## 3. Monitoring & Alerting

### 3.1 Dashboard Metrics

```python
# Key metrics to display
metrics = {
    "active_processes": int,
    "error_rate_percent": float,
    "avg_processing_time_ms": float,
    "feature_flag_status": {
        "image_analyzer": bool,
        "video_processor": bool,
        "stream_processor": bool,
    },
    "traffic_percentage": float,
}
```

### 3.2 Alert Thresholds

| Metric | Warning | Critical | Action |
|--------|---------|----------|--------|
| Error Rate | > 0.5% | > 2% | Auto-rollback |
| Avg Processing Time | > 110% baseline | > 150% baseline | Investigate/Rollback |
| Memory Usage | > 1.5GB | > 2.5GB | Scale/Restart |
| Failed Uploads | > 1% | > 5% | Investigate |

### 3.3 Alert Channels
- Slack: #ai-processor-alerts
- Email: dev-team@company.com
- PagerDuty: Critical alerts only

---

## 4. Rollback Procedures

### 4.1 Automatic Rollback
```python
# pseudo-code for automatic rollback
if error_rate > 0.02 or processing_time > baseline * 1.5:
    disable_feature_flags()
    notify_team("Automatic rollback triggered")
    preserve_logs_for_analysis()
```

### 4.2 Manual Rollback
```bash
# Option 1: Environment variables
set USE_REFACTORED_IMAGE_ANALYZER=false
set USE_REFACTORED_VIDEO_PROCESSOR=false
set USE_REFACTORED_STREAM_PROCESSOR=false

# Option 2: Restart with old config
docker-compose down
docker-compose -f docker-compose.old.yml up -d
```

### 4.3 Rollback Decision Tree
```
Error Rate > 2%?
├── Yes → Immediate rollback
└── No → Processing Time > 150% baseline?
    ├── Yes → Rollback after investigation
    └── No → Monitor and continue
```

---

## 5. Success Criteria

### 5.1 Functional
- [ ] Image analysis works for 99.9% of requests
- [ ] Video processing completes for 95%+ of uploads
- [ ] Stream processing stable for 24+ hours
- [ ] Resume functionality recovers 90%+ of interrupted jobs

### 5.2 Performance
- [ ] Image analysis: < 3 seconds (baseline: 2s)
- [ ] Video processing: < 120% of baseline time
- [ ] Stream processing: No frame drops > 5%
- [ ] Memory usage: < 2GB per worker

### 5.3 Monitoring
- [ ] Progress dashboard shows accurate %
- [ ] Error alerts fire correctly
- [ ] Rollback completes within 5 minutes
- [ ] All metrics logged for 30 days

---

## 6. Timeline Summary

| Day | Phase | Activity | Traffic % |
|-----|-------|----------|-----------|
| 1 | 1 | Staging test | 100% |
| 2 | 1 | Prod 10% rollout | 10% |
| 3 | 1 | Increase to 50% | 50% |
| 4 | 1 | Full rollout | 100% |
| 5-6 | 1 | Monitor & stabilize | 100% |
| 7 | 2 | Staging test video | 100% |
| 8 | 2 | Prod 10% rollout | 10% |
| 9 | 2 | Increase to 25% | 25% |
| 10 | 2 | Increase to 50% | 50% |
| 11-13 | 2 | Monitor & stabilize | 50-100% |
| 14 | 3 | Staging test stream | 100% |
| 15-21 | 3 | Gradual stream rollout | 5-100% |

---

## 7. Risk Mitigation

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| Feature flag fails to toggle | Low | High | Test toggle mechanism daily |
| Database batch insert fails | Medium | High | Fallback to single inserts |
| MinIO upload fails | Medium | Medium | Retry with exponential backoff |
| Memory leak in ThreadPool | Low | High | Monitor memory, auto-restart at 2GB |
| Resume state corruption | Low | Medium | Validate JSON before loading |
| SSE connection drops | Medium | Low | Auto-reconnect with progress query |

---

## 8. Post-Rollout

### 8.1 Cleanup (After 30 days stable)
- Remove old `ai_processor.py` code paths
- Remove Feature Flags for rolled out features
- Archive rollout documentation

### 8.2 Documentation
- Update API docs with new progress endpoints
- Document monitoring dashboard usage
- Create troubleshooting guide

### 8.3 Knowledge Transfer
- Demo session for ops team
- Document common issues and solutions
- Share lessons learned

---

## 9. Emergency Contacts

| Role | Name | Contact | Responsibility |
|------|------|---------|----------------|
| Tech Lead | [Name] | [Slack] | Go/No-Go decisions |
| DevOps | [Name] | [Pager] | Infrastructure |
| QA Lead | [Name] | [Slack] | Testing validation |
| On-Call | [Rotation] | [PagerDuty] | 24/7 support |

---

## 10. Quick Reference

### Enable Refactored Features (One by One)
```bash
# Image Analyzer
set USE_REFACTORED_IMAGE_ANALYZER=true

# Video Processor
set USE_REFACTORED_VIDEO_PROCESSOR=true

# Stream Processor
set USE_REFACTORED_STREAM_PROCESSOR=true
```

### Check Current Status
```bash
# View all feature flags
python -c "from config_loader import get_feature_flags_status; print(get_feature_flags_status())"
```

### Emergency Rollback
```bash
# Disable all refactored features
set USE_REFACTORED_IMAGE_ANALYZER=false
set USE_REFACTORED_VIDEO_PROCESSOR=false
set USE_REFACTORED_STREAM_PROCESSOR=false

# Restart services
docker-compose restart app
```

---

**Plan Version:** 1.0  
**Last Updated:** May 3, 2026  
**Next Review:** Day 7 of rollout
