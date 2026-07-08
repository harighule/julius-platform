use std::ffi::{c_uchar, c_int};
use rand::Rng;
use sha3::{Sha3_256, Digest};

#[no_mangle]
pub extern "C" fn sphinx_create_packet(
    _payload_ptr: *const c_uchar,
    payload_len: c_int,
    _path_ptr: *const c_uchar,
    _path_len: c_int,
) -> *mut c_uchar {
    let mut rng = rand::thread_rng();
    let mut packet = vec![0u8; 1088];
    rng.fill(&mut packet[..]);
    let ptr = packet.as_mut_ptr();
    std::mem::forget(packet);
    ptr
}

#[no_mangle]
pub extern "C" fn sphinx_free_packet(ptr: *mut c_uchar) {
    if !ptr.is_null() {
        unsafe { drop(Vec::from_raw_parts(ptr, 0, 1088)); }
    }
}

#[no_mangle]
pub extern "C" fn sphinx_process_hop(
    packet_ptr: *const c_uchar,
    packet_len: c_int,
    _key_ptr: *const c_uchar,
    _key_len: c_int,
    out_ptr: *mut c_uchar,
) -> c_int {
    unsafe {
        let packet = std::slice::from_raw_parts(packet_ptr, packet_len as usize);
        let out = std::slice::from_raw_parts_mut(out_ptr, packet_len as usize);
        out.copy_from_slice(packet);
    }
    0
}
