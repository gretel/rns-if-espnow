# Security Analysis of ESP-NOW Implementation

> https://github.com/espressif/esp-now/blob/master/src/espnow/src/espnow.c @ 3f288c8

## Buffer Overflow Vulnerabilities

### 1. Dynamic Memory Allocation Without Size Verification

```c
espnow_data_t *espnow_data = ESP_MALLOC(sizeof(espnow_data_t) + size);
```

In the espnow_send() function, while there is a size check against ESPNOW_DATA_LEN, the allocation adds size to sizeof(espnow_data_t) without verifying their sum won't overflow. This could lead to integer overflow in the allocation size calculation.

### 2. Insufficient Bounds Checking in Group Processing

```c
memcpy(group_info->addrs_list, addrs_list + i * 32, send_addrs_num * ESPNOW_ADDR_LEN);
```

In espnow_set_group(), the code processes address lists in chunks of 32. While there's a basic size check, there's no validation that i * 32 won't exceed the bounds of addrs_list. An attacker could potentially craft input that causes buffer overflow.

### 3. Queue Buffer Management Issues

The espnow_recv_cb() function processes incoming packets and places them in queues. While there are some size checks, there are scenarios where buffer boundaries might not be properly validated:

```c
espnow_pkt_t *q_data = ESP_MALLOC(sizeof(espnow_pkt_t) + espnow_data->size);
```

The allocation depends on untrusted input (espnow_data->size) from the network.

## Security Design Issues

### 1. Encryption Key Management

The code stores encryption keys in memory and NVS (Non-Volatile Storage):
```c
static uint8_t g_espnow_sec_key[APP_KEY_LEN] = {0};
```

- Keys remain in memory even after use
- No secure key erasure mechanism
- Keys stored in NVS without additional protection

### 2. Magic Number Verification

The code uses a magic number system for message deduplication:
```c
if (g_msg_magic_cache[index].magic == frame_head->magic) {
    return;
}
```

This system is vulnerable to:
- Replay attacks if an attacker captures valid magic numbers
- Potential DoS by flooding with packets using predicted magic numbers

### 3. Channel Switching Vulnerabilities

```c
if (frame_head->channel == ESPNOW_CHANNEL_ALL && g_set_channel_flag) {
    esp_wifi_set_channel(g_self_country.schan + i, WIFI_SECOND_CHAN_NONE);
}
```

The channel switching mechanism could be exploited to:
- Cause denial of service by forcing frequent channel switches
- Create timing vulnerabilities during channel transitions

## Input Validation Issues

### 1. Type Validation Gaps

```c
if (espnow_data->version != ESPNOW_VERSION || (espnow_data->type >= ESPNOW_DATA_TYPE_MAX))
```

While there's basic type validation, the code doesn't fully validate all possible type combinations and state transitions.

### 2. Address Validation

```c
ESP_PARAM_CHECK(dest_addr);
```

The address validation is basic and doesn't check for:
- Valid address formats
- Allowed address ranges
- Potential malicious addresses

## Recommendations

1. **Memory Management**
   - Add overflow checks for all dynamic allocations
   - Implement size validation before memory operations
   - Use secure memory wiping for sensitive data

2. **Input Validation**
   - Implement comprehensive input validation for all network-sourced data
   - Add state validation for all packet types
   - Validate addresses against allowed ranges

3. **Cryptographic Improvements**
   - Implement secure key storage
   - Add key rotation mechanism
   - Implement proper key destruction

4. **Protocol Hardening**
   - Add sequence numbers for replay protection
   - Implement rate limiting
   - Add more robust peer authentication

5. **System Protection**
   - Add rate limiting for channel switching
   - Implement resource usage monitoring
   - Add DoS protection mechanisms