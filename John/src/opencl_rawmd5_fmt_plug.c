/*
 * MD5 OpenCL code is based on Alain Espinosa's OpenCL patches.
 *
 * This software is Copyright (c) 2010, Dhiru Kholia <dhiru.kholia at gmail.com>
 * and Copyright (c) 2012, magnum
 * and Copyright (c) 2015, Sayantan Datta <std2048@gmail.com>
 * and it is hereby released to the general public under the following terms:
 * Redistribution and use in source and binary forms, with or without
 * modification, are permitted.
 */

#ifdef HAVE_OPENCL
#define FMT_STRUCT fmt_opencl_rawMD5

#if FMT_EXTERNS_H
extern struct fmt_main FMT_STRUCT;
#elif FMT_REGISTERS_H
john_register_one(&FMT_STRUCT);
#else

#include <string.h>
#include <assert.h>

#include "arch.h"
#include "params.h"
#include "path.h"
#include "common.h"
#include "formats.h"
#include "common-opencl.h"
#include "config.h"
#include "options.h"
#include "mask_ext.h"
#include "interface.h"

#define PLAINTEXT_LENGTH    55 /* Max. is 55 with current kernel */
#define BUFSIZE             ((PLAINTEXT_LENGTH+3)/4*4)
#define FORMAT_LABEL        "Raw-MD5-opencl"
#define FORMAT_NAME         ""
#define ALGORITHM_NAME      "MD5 OpenCL"
#define BENCHMARK_COMMENT   ""
#define BENCHMARK_LENGTH    -1
#define CIPHERTEXT_LENGTH   32
#define DIGEST_SIZE         16
#define BINARY_SIZE         16
#define BINARY_ALIGN        1
#define SALT_SIZE           0
#define SALT_ALIGN          1

#define FORMAT_TAG          "$dynamic_0$"
#define TAG_LENGTH          (sizeof(FORMAT_TAG) - 1)

static cl_mem pinned_saved_keys, pinned_saved_idx, pinned_int_key_loc;
static cl_mem buffer_keys, buffer_idx, buffer_int_keys, buffer_int_key_loc;
static cl_uint *saved_plain, *saved_idx, *saved_int_key_loc;
static int static_gpu_locations[MASK_FMT_INT_PLHDR];

static cl_mem buffer_offset_table, buffer_hash_table, buffer_return_hashes, buffer_hash_ids, buffer_bitmap_dupe, buffer_bitmaps;
static OFFSET_TABLE_WORD *offset_table = NULL;
static cl_uint *loaded_hashes = NULL, num_loaded_hashes, *hash_ids = NULL, *bitmaps = NULL;
static unsigned int hash_table_size, offset_table_size, shift64_ht_sz, shift64_ot_sz;
static cl_ulong bitmap_size_bits = 0;

static unsigned int key_idx = 0;
static unsigned int ref_ctr, ocl_ver;
static struct fmt_main *self;

#define MIN_KEYS_PER_CRYPT      1
#define MAX_KEYS_PER_CRYPT      1

#define STEP                    0
#define SEED                    1024

#define get_power_of_two(v)	\
{				\
	v--;			\
	v |= v >> 1;		\
	v |= v >> 2;		\
	v |= v >> 4;		\
	v |= v >> 8;		\
	v |= v >> 16;		\
	v |= v >> 32;		\
	v++;			\
}

static const char * warn[] = {
	"pass xfer: ", ", index xfer: ", ", key_loc xfer: ",
	 ", fill_buffer_0: ", ", fill_buffer_1: ", ", crypt: ",
	 ", num_cracked xfer: ", ", result xfer: ", ", result_data xfer: "
};

static int crypt_all(int *pcount, struct db_salt *_salt);

//This file contains auto-tuning routine(s). It has to be included after formats definitions.
#include "opencl-autotune.h"
#include "memdbg.h"

static struct fmt_tests tests[] = {
	{"5a105e8b9d40e1329780d62ea2265d8a", "test1"},
	{FORMAT_TAG "5a105e8b9d40e1329780d62ea2265d8a", "test1"},
	{"098f6bcd4621d373cade4e832627b4f6", "test"},
	{FORMAT_TAG "378e2c4a07968da2eca692320136433d", "thatsworking"},
	{FORMAT_TAG "8ad8757baa8564dc136c1e07507f4a98", "test3"},
	{"d41d8cd98f00b204e9800998ecf8427e", ""},
#ifdef DEBUG
	{FORMAT_TAG "c9ccf168914a1bcfc3229f1948e67da0","1234567890123456789012345678901234567890123456789012345"},
#if PLAINTEXT_LENGTH >= 80
	{FORMAT_TAG "57edf4a22be3c955ac49da2e2107b67a","12345678901234567890123456789012345678901234567890123456789012345678901234567890"},
#endif
#endif
	{NULL}
};

struct fmt_main FMT_STRUCT;

/* ------- Helper functions ------- */
static size_t get_task_max_work_group_size()
{
	return autotune_get_task_max_work_group_size(FALSE, 0, crypt_kernel);
}

static size_t get_task_max_size()
{
	return 0;
}

static size_t get_default_workgroup()
{
	return 0;
}

static void set_kernel_args()
{
	HANDLE_CLERROR(clSetKernelArg(crypt_kernel, 0, sizeof(buffer_keys), (void *) &buffer_keys), "Error setting argument 1.");
	HANDLE_CLERROR(clSetKernelArg(crypt_kernel, 1, sizeof(buffer_idx), (void *) &buffer_idx), "Error setting argument 2.");
	HANDLE_CLERROR(clSetKernelArg(crypt_kernel, 2, sizeof(buffer_int_key_loc), (void *) &buffer_int_key_loc), "Error setting argument 3.");
	HANDLE_CLERROR(clSetKernelArg(crypt_kernel, 3, sizeof(buffer_int_keys), (void *) &buffer_int_keys), "Error setting argument 4.");
	HANDLE_CLERROR(clSetKernelArg(crypt_kernel, 4, sizeof(buffer_bitmaps), (void *) &buffer_bitmaps), "Error setting argument 5.");
	HANDLE_CLERROR(clSetKernelArg(crypt_kernel, 5, sizeof(buffer_offset_table), (void *) &buffer_offset_table), "Error setting argument 6.");
	HANDLE_CLERROR(clSetKernelArg(crypt_kernel, 6, sizeof(buffer_hash_table), (void *) &buffer_hash_table), "Error setting argument 7.");
	HANDLE_CLERROR(clSetKernelArg(crypt_kernel, 7, sizeof(buffer_return_hashes), (void *) &buffer_return_hashes), "Error setting argument 8.");
	HANDLE_CLERROR(clSetKernelArg(crypt_kernel, 8, sizeof(buffer_hash_ids), (void *) &buffer_hash_ids), "Error setting argument 9.");
	HANDLE_CLERROR(clSetKernelArg(crypt_kernel, 9, sizeof(buffer_bitmap_dupe), (void *) &buffer_bitmap_dupe), "Error setting argument 10.");
}

static void create_clobj(size_t kpc, struct fmt_main *self)
{
	cl_ulong max_alloc_size_bytes = 0;
	cl_ulong cache_size_bytes = 0;

	HANDLE_CLERROR(clGetDeviceInfo(devices[gpu_id], CL_DEVICE_MAX_MEM_ALLOC_SIZE, sizeof(cl_ulong), &max_alloc_size_bytes, 0), "failed to get CL_DEVICE_MAX_MEM_ALLOC_SIZE.");
	HANDLE_CLERROR(clGetDeviceInfo(devices[gpu_id], CL_DEVICE_GLOBAL_MEM_CACHE_SIZE, sizeof(cl_ulong), &cache_size_bytes, 0), "failed to get CL_DEVICE_GLOBAL_MEM_CACHE_SIZE.");

	if (max_alloc_size_bytes & (max_alloc_size_bytes - 1)) {
		get_power_of_two(max_alloc_size_bytes);
		max_alloc_size_bytes >>= 1;
	}
	if (max_alloc_size_bytes >= 536870912) max_alloc_size_bytes = 536870912;
	assert(!(max_alloc_size_bytes & (max_alloc_size_bytes - 1)));

	if (!cache_size_bytes) cache_size_bytes = 1024;

	pinned_saved_keys = clCreateBuffer(context[gpu_id], CL_MEM_READ_ONLY | CL_MEM_ALLOC_HOST_PTR, BUFSIZE * kpc, NULL, &ret_code);
	if (ret_code != CL_SUCCESS) {
		saved_plain = (cl_uint *) mem_alloc(BUFSIZE * kpc);
		if (saved_plain == NULL)
			HANDLE_CLERROR(ret_code, "Error creating page-locked memory pinned_saved_keys.");
	}
	else {
		saved_plain = (cl_uint *) clEnqueueMapBuffer(queue[gpu_id], pinned_saved_keys, CL_TRUE, CL_MAP_READ | CL_MAP_WRITE, 0, BUFSIZE * kpc, 0, NULL, NULL, &ret_code);
		HANDLE_CLERROR(ret_code, "Error mapping page-locked memory saved_plain.");
	}

	pinned_saved_idx = clCreateBuffer(context[gpu_id], CL_MEM_READ_ONLY | CL_MEM_ALLOC_HOST_PTR, sizeof(cl_uint) * kpc, NULL, &ret_code);
	HANDLE_CLERROR(ret_code, "Error creating page-locked memory pinned_saved_idx.");
	saved_idx = (cl_uint *) clEnqueueMapBuffer(queue[gpu_id], pinned_saved_idx, CL_TRUE, CL_MAP_READ | CL_MAP_WRITE, 0, sizeof(cl_uint) * kpc, 0, NULL, NULL, &ret_code);
	HANDLE_CLERROR(ret_code, "Error mapping page-locked memory saved_idx.");

	pinned_int_key_loc = clCreateBuffer(context[gpu_id], CL_MEM_READ_ONLY | CL_MEM_ALLOC_HOST_PTR, sizeof(cl_uint) * kpc, NULL, &ret_code);
	HANDLE_CLERROR(ret_code, "Error creating page-locked memory pinned_int_key_loc.");
	saved_int_key_loc = (cl_uint *) clEnqueueMapBuffer(queue[gpu_id], pinned_int_key_loc, CL_TRUE, CL_MAP_READ | CL_MAP_WRITE, 0, sizeof(cl_uint) * kpc, 0, NULL, NULL, &ret_code);
	HANDLE_CLERROR(ret_code, "Error mapping page-locked memory saved_int_key_loc.");

	// create and set arguments
	buffer_keys = clCreateBuffer(context[gpu_id], CL_MEM_READ_ONLY, BUFSIZE * kpc, NULL, &ret_code);
	HANDLE_CLERROR(ret_code, "Error creating buffer argument buffer_keys.");

	buffer_idx = clCreateBuffer(context[gpu_id], CL_MEM_READ_ONLY, 4 * kpc, NULL, &ret_code);
	HANDLE_CLERROR(ret_code, "Error creating buffer argument buffer_idx.");

	buffer_int_key_loc = clCreateBuffer(context[gpu_id], CL_MEM_READ_ONLY, sizeof(cl_uint) * kpc, NULL, &ret_code);
	HANDLE_CLERROR(ret_code, "Error creating buffer argument buffer_int_key_loc.");

	buffer_return_hashes = clCreateBuffer(context[gpu_id], CL_MEM_WRITE_ONLY, 2 * sizeof(cl_uint) * num_loaded_hashes, NULL, &ret_code);
	HANDLE_CLERROR(ret_code, "Error creating buffer argument buffer_return_hashes.");

	buffer_hash_ids = clCreateBuffer(context[gpu_id], CL_MEM_READ_WRITE, (3 * num_loaded_hashes + 1) * sizeof(cl_uint), NULL, &ret_code);
	HANDLE_CLERROR(ret_code, "Error creating buffer argument buffer_buffer_hash_ids.");

	buffer_bitmap_dupe = clCreateBuffer(context[gpu_id], CL_MEM_READ_WRITE, (hash_table_size/32 + 1) * sizeof(cl_uint), NULL, &ret_code);
	HANDLE_CLERROR(ret_code, "Error creating buffer argument buffer_bitmap_dupe.");

	buffer_bitmaps = clCreateBuffer(context[gpu_id], CL_MEM_READ_WRITE, max_alloc_size_bytes, NULL, &ret_code);
	HANDLE_CLERROR(ret_code, "Error creating buffer argument buffer_bitmaps.");

	//ref_ctr is used as dummy parameter
	buffer_int_keys = clCreateBuffer(context[gpu_id], CL_MEM_READ_ONLY | CL_MEM_COPY_HOST_PTR, 4 * mask_int_cand.num_int_cand, mask_int_cand.int_cand ? mask_int_cand.int_cand : (void *)&ref_ctr, &ret_code);
	HANDLE_CLERROR(ret_code, "Error creating buffer argument buffer_int_keys.");

	buffer_offset_table = clCreateBuffer(context[gpu_id], CL_MEM_READ_ONLY, offset_table_size * sizeof(OFFSET_TABLE_WORD), NULL, &ret_code);
	HANDLE_CLERROR(ret_code, "Error creating buffer argument buffer_offset_table.");

	buffer_hash_table = clCreateBuffer(context[gpu_id], CL_MEM_READ_ONLY, hash_table_size * sizeof(unsigned int) * 2, NULL, &ret_code);
	HANDLE_CLERROR(ret_code, "Error creating buffer argument buffer_hash_table.");

	set_kernel_args();

	ref_ctr++;
}

static void release_clobj(void)
{
	if (ref_ctr) {
		if (pinned_saved_keys) {
			HANDLE_CLERROR(clEnqueueUnmapMemObject(queue[gpu_id], pinned_saved_keys, saved_plain, 0, NULL, NULL), "Error Unmapping saved_plain.");
			HANDLE_CLERROR(clReleaseMemObject(pinned_saved_keys), "Error Releasing pinned_saved_keys.");
		}
		else
			MEM_FREE(saved_plain);
		HANDLE_CLERROR(clEnqueueUnmapMemObject(queue[gpu_id], pinned_saved_idx, saved_idx, 0, NULL, NULL), "Error Unmapping saved_idx.");
		HANDLE_CLERROR(clEnqueueUnmapMemObject(queue[gpu_id], pinned_int_key_loc, saved_int_key_loc, 0, NULL, NULL), "Error Unmapping saved_int_key_loc.");
		HANDLE_CLERROR(clFinish(queue[gpu_id]), "Error releasing mappings.");
		HANDLE_CLERROR(clReleaseMemObject(buffer_keys), "Error Releasing buffer_keys.");
		HANDLE_CLERROR(clReleaseMemObject(buffer_idx), "Error Releasing buffer_idx.");
		HANDLE_CLERROR(clReleaseMemObject(buffer_int_key_loc), "Error Releasing buffer_int_key_loc.");
		HANDLE_CLERROR(clReleaseMemObject(buffer_int_keys), "Error Releasing buffer_int_keys.");
		HANDLE_CLERROR(clReleaseMemObject(buffer_return_hashes), "Error Releasing buffer_return_hashes.");
		HANDLE_CLERROR(clReleaseMemObject(buffer_offset_table), "Error Releasing buffer_offset_table.");
		HANDLE_CLERROR(clReleaseMemObject(buffer_hash_table), "Error Releasing buffer_hash_table.");
		HANDLE_CLERROR(clReleaseMemObject(buffer_bitmap_dupe), "Error Releasing buffer_bitmap_dupe.");
		HANDLE_CLERROR(clReleaseMemObject(buffer_bitmaps), "Error Releasing buffer_bitmap.");

		HANDLE_CLERROR(clReleaseMemObject(pinned_saved_idx), "Error Releasing pinned_saved_idx.");
		HANDLE_CLERROR(clReleaseMemObject(pinned_int_key_loc), "Error Releasing pinned_int_key_loc.");

		ref_ctr--;
	}
}

static void done(void)
{
	release_clobj();

	if (crypt_kernel) {
		HANDLE_CLERROR(clReleaseKernel(crypt_kernel), "Release kernel.");
		HANDLE_CLERROR(clReleaseProgram(program[gpu_id]), "Release Program.");

		crypt_kernel = NULL;
	}

	if (loaded_hashes)
		MEM_FREE(loaded_hashes);
	if (hash_ids)
		MEM_FREE(hash_ids);
	if (bitmaps)
		MEM_FREE(bitmaps);
	if (offset_table)
		MEM_FREE(offset_table);
	if (hash_table_128)
		MEM_FREE(hash_table_128);
}

static void init_kernel(unsigned int num_ld_hashes, char *bitmap_para)
{
	char build_opts[5000];
	int i;
	cl_ulong const_cache_size;
	
	clReleaseKernel(crypt_kernel);

	shift64_ht_sz = (((1ULL << 63) % hash_table_size) * 2) % hash_table_size;
	shift64_ot_sz = (((1ULL << 63) % offset_table_size) * 2) % offset_table_size;

	for (i = 0; i < MASK_FMT_INT_PLHDR; i++)
		if (mask_skip_ranges!= NULL && mask_skip_ranges[i] != -1)
			static_gpu_locations[i] = mask_int_cand.int_cpu_mask_ctx->
				ranges[mask_skip_ranges[i]].pos;
		else
			static_gpu_locations[i] = -1;

	ocl_ver = get_device_version(gpu_id);

	/* Driver bug workaround for OSX and GT650M, see #1459 */
	if (ocl_ver == 120 && platform_apple(platform_id) && gpu_nvidia(gpu_id))
		ocl_ver = 110;

	HANDLE_CLERROR(clGetDeviceInfo(devices[gpu_id], CL_DEVICE_MAX_CONSTANT_BUFFER_SIZE, sizeof(cl_ulong), &const_cache_size, 0), "failed to get CL_DEVICE_MAX_CONSTANT_BUFFER_SIZE.");

	sprintf(build_opts, "-D OFFSET_TABLE_SIZE=%u -D HASH_TABLE_SIZE=%u"
		" -D SHIFT64_OT_SZ=%u -D SHIFT64_HT_SZ=%u -D NUM_LOADED_HASHES=%u"
		" -D NUM_INT_KEYS=%u %s -D IS_STATIC_GPU_MASK=%d"
		" -D CONST_CACHE_SIZE=%llu -D LOC_0=%d"
#if 1 < MASK_FMT_INT_PLHDR
	" -D LOC_1=%d "
#endif
#if 2 < MASK_FMT_INT_PLHDR
	"-D LOC_2=%d "
#endif
#if 3 < MASK_FMT_INT_PLHDR
	"-D LOC_3=%d"
#endif
	, offset_table_size, hash_table_size, shift64_ot_sz, shift64_ht_sz,
	num_ld_hashes, mask_int_cand.num_int_cand, bitmap_para, is_static_gpu_mask,
	(unsigned long long)const_cache_size, static_gpu_locations[0]
#if 1 < MASK_FMT_INT_PLHDR
	, static_gpu_locations[1]
#endif
#if 2 < MASK_FMT_INT_PLHDR
	, static_gpu_locations[2]
#endif
#if 3 < MASK_FMT_INT_PLHDR
	, static_gpu_locations[3]
#endif
	);

	opencl_build(gpu_id, build_opts, 0, NULL);
	crypt_kernel = clCreateKernel(program[gpu_id], "md5", &ret_code);
	HANDLE_CLERROR(ret_code, "Error creating kernel. Double-check kernel name?");
}

static void init(struct fmt_main *_self)
{
	self = _self;
	num_loaded_hashes = 0;
	mask_int_cand_target = 10000;

	opencl_prepare_dev(gpu_id);

	opencl_read_source("$JOHN/kernels/md5_kernel.cl");
}

static int valid(char *ciphertext, struct fmt_main *self)
{
	char *p, *q;

	p = ciphertext;
	if (!strncmp(p, FORMAT_TAG, TAG_LENGTH))
		p += TAG_LENGTH;

	q = p;
	while (atoi16[ARCH_INDEX(*q)] != 0x7F) {
		if (*q >= 'A' && *q <= 'F') /* support lowercase only */
			return 0;
		q++;
	}
	return !*q && q - p == CIPHERTEXT_LENGTH;
}

static char *split(char *ciphertext, int index, struct fmt_main *self)
{
	static char out[TAG_LENGTH + CIPHERTEXT_LENGTH + 1];

	if (!strncmp(ciphertext, FORMAT_TAG, TAG_LENGTH))
		return ciphertext;

	memcpy(out, FORMAT_TAG, TAG_LENGTH);
	memcpy(out + TAG_LENGTH, ciphertext, CIPHERTEXT_LENGTH + 1);
	return out;
}

static void *get_binary(char *ciphertext)
{
	static unsigned char out[DIGEST_SIZE];
	char *p;
	int i;
	p = ciphertext + TAG_LENGTH;
	for (i = 0; i < sizeof(out); i++) {
		out[i] = (atoi16[ARCH_INDEX(*p)] << 4) | atoi16[ARCH_INDEX(p[1])];
		p += 2;
	}
	return out;
}

static int get_hash_0(int index) { return hash_table_128[hash_ids[3 + 3 * index]] & 0xf; }
static int get_hash_1(int index) { return hash_table_128[hash_ids[3 + 3 * index]] & 0xff; }
static int get_hash_2(int index) { return hash_table_128[hash_ids[3 + 3 * index]] & 0xfff; }
static int get_hash_3(int index) { return hash_table_128[hash_ids[3 + 3 * index]] & 0xffff; }
static int get_hash_4(int index) { return hash_table_128[hash_ids[3 + 3 * index]] & 0xfffff; }
static int get_hash_5(int index) { return hash_table_128[hash_ids[3 + 3 * index]] & 0xffffff; }
static int get_hash_6(int index) { return hash_table_128[hash_ids[3 + 3 * index]] & 0x7ffffff; }

static void clear_keys(void)
{
	key_idx = 0;
}

static void set_key(char *_key, int index)
{
	const ARCH_WORD_32 *key = (ARCH_WORD_32*)_key;
	int len = strlen(_key);

	if (mask_int_cand.num_int_cand > 1 && !is_static_gpu_mask) {
		int i;
		saved_int_key_loc[index] = 0;
		for (i = 0; i < MASK_FMT_INT_PLHDR; i++) {
			if (mask_skip_ranges[i] != -1)  {
				saved_int_key_loc[index] |= ((mask_int_cand.
				int_cpu_mask_ctx->ranges[mask_skip_ranges[i]].offset +
				mask_int_cand.int_cpu_mask_ctx->
				ranges[mask_skip_ranges[i]].pos) & 0xff) << (i << 3);
			}
			else
				saved_int_key_loc[index] |= 0x80 << (i << 3);
		}
	}

	saved_idx[index] = (key_idx << 6) | len;

	while (len > 4) {
		saved_plain[key_idx++] = *key++;
		len -= 4;
	}
	if (len)
		saved_plain[key_idx++] = *key & (0xffffffffU >> (32 - (len << 3)));
}

static char *get_key(int index)
{
	static char out[PLAINTEXT_LENGTH + 1];
	int i, len, int_index, t;
	char *key;

	if (hash_ids == NULL || hash_ids[0] == 0 ||
	    index > hash_ids[0] || hash_ids[0] > num_loaded_hashes) {
		t = index;
		int_index = 0;
	}
	else  {
		t = hash_ids[1 + 3 * index];
		int_index = hash_ids[2 + 3 * index];

	}

	if (t > global_work_size) {
		fprintf(stderr, "Get key error! %d %d\n", t, index);
		t = 0;
	}

	len = saved_idx[t] & 63;
	key = (char*)&saved_plain[saved_idx[t] >> 6];

	for (i = 0; i < len; i++)
		out[i] = *key++;
	out[i] = 0;

	if (mask_int_cand.num_int_cand > 1) {
		for (i = 0; i < MASK_FMT_INT_PLHDR && mask_skip_ranges[i] != -1; i++)
			if (is_static_gpu_mask)
				out[static_gpu_locations[i]] =
				mask_int_cand.int_cand[int_index].x[i];
			else
				out[(saved_int_key_loc[t]& (0xff << (i * 8))) >> (i * 8)] =
				mask_int_cand.int_cand[int_index].x[i];
	}

	return out;
}

static void prepare_table(struct db_salt *salt) {
	unsigned int *bin, i;
	struct db_password *pw;

	num_loaded_hashes = (salt->count);

	MEM_FREE(loaded_hashes);
	MEM_FREE(hash_ids);
	MEM_FREE(offset_table);
	MEM_FREE(hash_table_128);

	loaded_hashes = (cl_uint*) mem_alloc(4 * num_loaded_hashes * sizeof(cl_uint));
	hash_ids = (cl_uint*) mem_alloc((3 * num_loaded_hashes + 1) * sizeof(cl_uint));

	pw = salt -> list;
	i = 0;
	do {
		bin = (unsigned int *)pw -> binary;
		// Potential segfault if removed
		if(bin != NULL) {
			loaded_hashes[4 * i] = bin[0];
			loaded_hashes[4 * i + 1] = bin[1];
			loaded_hashes[4 * i + 2] = bin[2];
			loaded_hashes[4 * i + 3] = bin[3];
			i++ ;
		}
	} while ((pw = pw -> next)) ;

	if(i != (salt->count)) {
		fprintf(stderr,
			"Something went wrong while preparing hashes..Exiting..\n");
		error();
	}

	num_loaded_hashes = create_perfect_hash_table(128, (void *)loaded_hashes,
				num_loaded_hashes,
			        &offset_table,
			        &offset_table_size,
			        &hash_table_size, 0);

	if (!num_loaded_hashes) {
		MEM_FREE(hash_table_128);
		MEM_FREE(offset_table);
		fprintf(stderr, "Failed to create Hash Table for cracking.\n");
		error();
	}
}

/* Use only for smaller bitmaps < 16MB */
static void prepare_bitmap_8(cl_ulong bmp_sz, cl_uint **bitmap_ptr)
{
	unsigned int i;
	MEM_FREE(*bitmap_ptr);
	*bitmap_ptr = (cl_uint*) mem_calloc((bmp_sz >> 2), sizeof(cl_uint));

	for (i = 0; i < num_loaded_hashes; i++) {
		unsigned int bmp_idx =
			(loaded_hashes[4 * i] & 0x0000ffff) & (bmp_sz - 1);
		(*bitmap_ptr)[bmp_idx >> 5] |= (1U << (bmp_idx & 31));

		bmp_idx = (loaded_hashes[4 * i] >> 16) & (bmp_sz - 1);
		(*bitmap_ptr)[(bmp_sz >> 5) + (bmp_idx >> 5)] |=
			(1U << (bmp_idx & 31));

		bmp_idx = (loaded_hashes[4 * i + 1] & 0x0000ffff) & (bmp_sz - 1);
		(*bitmap_ptr)[(bmp_sz >> 4) + (bmp_idx >> 5)] |=
			(1U << (bmp_idx & 31));

		bmp_idx = (loaded_hashes[4 * i + 1] >> 16) & (bmp_sz - 1);
		(*bitmap_ptr)[(bmp_sz >> 5) * 3 + (bmp_idx >> 5)] |=
			(1U << (bmp_idx & 31));

		bmp_idx = (loaded_hashes[4 * i + 2] & 0x0000ffff) & (bmp_sz - 1);
		(*bitmap_ptr)[(bmp_sz >> 3) + (bmp_idx >> 5)] |=
			(1U << (bmp_idx & 31));

		bmp_idx = (loaded_hashes[4 * i + 2] >> 16) & (bmp_sz - 1);
		(*bitmap_ptr)[(bmp_sz >> 5) * 5 + (bmp_idx >> 5)] |=
			(1U << (bmp_idx & 31));

		bmp_idx = (loaded_hashes[4 * i + 3] & 0x0000ffff) & (bmp_sz - 1);
		(*bitmap_ptr)[(bmp_sz >> 5) * 6 + (bmp_idx >> 5)] |=
			(1U << (bmp_idx & 31));

		bmp_idx = (loaded_hashes[4 * i + 3] >> 16) & (bmp_sz - 1);
		(*bitmap_ptr)[(bmp_sz >> 5) * 7 + (bmp_idx >> 5)] |=
			(1U << (bmp_idx & 31));
	}
}

/* Use only for smaller bitmaps < 16MB */
static void prepare_bitmap_4(cl_ulong bmp_sz, cl_uint **bitmap_ptr)
{
	unsigned int i;
	MEM_FREE(*bitmap_ptr);
	*bitmap_ptr = (cl_uint*) mem_calloc((bmp_sz >> 3), sizeof(cl_uint));

	for (i = 0; i < num_loaded_hashes; i++) {
		unsigned int bmp_idx = loaded_hashes[4 * i + 3] & (bmp_sz - 1);
		(*bitmap_ptr)[bmp_idx >> 5] |= (1U << (bmp_idx & 31));

		bmp_idx = loaded_hashes[4 * i + 2] & (bmp_sz - 1);
		(*bitmap_ptr)[(bmp_sz >> 5) + (bmp_idx >> 5)] |=
			(1U << (bmp_idx & 31));

		bmp_idx = loaded_hashes[4 * i + 1] & (bmp_sz - 1);
		(*bitmap_ptr)[(bmp_sz >> 4) + (bmp_idx >> 5)] |=
			(1U << (bmp_idx & 31));

		bmp_idx = loaded_hashes[4 * i] & (bmp_sz - 1);
		(*bitmap_ptr)[(bmp_sz >> 5) * 3 + (bmp_idx >> 5)] |=
			(1U << (bmp_idx & 31));
	}
}

static void prepare_bitmap_1(cl_ulong bmp_sz, cl_uint **bitmap_ptr)
{
	unsigned int i;
	MEM_FREE(*bitmap_ptr);
	*bitmap_ptr = (cl_uint*) mem_calloc((bmp_sz >> 5), sizeof(cl_uint));

	for (i = 0; i < num_loaded_hashes; i++) {
		unsigned int bmp_idx = loaded_hashes[4 * i + 3] & (bmp_sz - 1);
		(*bitmap_ptr)[bmp_idx >> 5] |= (1U << (bmp_idx & 31));
	}
}

static char* select_bitmap(unsigned int num_ld_hashes)
{	static char kernel_params[200];
	cl_ulong max_local_mem_sz_bytes = 0;
	unsigned int cmp_steps = 2, use_local = 0;

	HANDLE_CLERROR(clGetDeviceInfo(devices[gpu_id], CL_DEVICE_LOCAL_MEM_SIZE,
		sizeof(cl_ulong), &max_local_mem_sz_bytes, 0),
		"failed to get CL_DEVICE_LOCAL_MEM_SIZE.");

	if (num_loaded_hashes <= 5100) {
		if (amd_gcn_10(device_info[gpu_id]) ||
			amd_vliw4(device_info[gpu_id]))
			bitmap_size_bits = 512 * 1024;

		else if (amd_gcn_11(device_info[gpu_id]) ||
			max_local_mem_sz_bytes < 16384)
			bitmap_size_bits = 256 * 1024;

		else {
			bitmap_size_bits = 32 * 1024;
			cmp_steps = 4;
			use_local = 1;
		}
	}

	else if (num_loaded_hashes <= 10100) {
		if (amd_gcn_10(device_info[gpu_id]) ||
			amd_vliw4(device_info[gpu_id]))
			bitmap_size_bits = 512 * 1024;

		else if (amd_gcn_11(device_info[gpu_id]) ||
			max_local_mem_sz_bytes < 32768)
			bitmap_size_bits = 256 * 1024;

		else {
			bitmap_size_bits = 64 * 1024;
			cmp_steps = 4;
			use_local = 1;
		}
	}

	else if (num_loaded_hashes <= 20100) {
		if (amd_gcn_10(device_info[gpu_id]))
			bitmap_size_bits = 1024 * 1024;

		else if (amd_gcn_11(device_info[gpu_id]) ||
			max_local_mem_sz_bytes < 32768)
			bitmap_size_bits = 512 * 1024;

		else if (amd_vliw4(device_info[gpu_id])) {
			bitmap_size_bits = 256 * 1024;
			cmp_steps = 4;
		}

		else {
			bitmap_size_bits = 32 * 1024;
			cmp_steps = 8;
			use_local = 1;
		}
	}

	else if (num_loaded_hashes <= 250100)
		bitmap_size_bits = 2048 * 1024;

	else if (num_loaded_hashes <= 1100100) {
		if (!amd_gcn_11(device_info[gpu_id]))
			bitmap_size_bits = 4096 * 1024;

		else
			bitmap_size_bits = 2048 * 1024;
	}

	else if (num_loaded_hashes <= 1500100) {
		bitmap_size_bits = 4096 * 1024 * 2;
		cmp_steps = 1;
	}

	else if (num_loaded_hashes <= 2700100) {
		bitmap_size_bits = 4096 * 1024 * 2 * 2;
		cmp_steps = 1;
	}

	else {
		cl_ulong mult = num_loaded_hashes / 2700100;
		cl_ulong buf_sz;
		bitmap_size_bits = 4096 * 4096;
		get_power_of_two(mult);
		bitmap_size_bits *= mult;
		HANDLE_CLERROR(clGetMemObjectInfo(buffer_bitmaps, CL_MEM_SIZE,
			sizeof(size_t), &buf_sz, NULL),
			"failed to query buffer_bitmaps.");
		if ((bitmap_size_bits >> 3) > buf_sz)
			bitmap_size_bits = buf_sz << 3;
		assert(!(bitmap_size_bits & (bitmap_size_bits - 1)));
		cmp_steps = 1;
	}

	if (cmp_steps == 1)
		prepare_bitmap_1(bitmap_size_bits, &bitmaps);

	else if (cmp_steps <= 4)
		prepare_bitmap_4(bitmap_size_bits, &bitmaps);

	else
		prepare_bitmap_8(bitmap_size_bits, &bitmaps);

	sprintf(kernel_params,
		"-D SELECT_CMP_STEPS=%u"
		" -D BITMAP_SIZE_BITS_LESS_ONE="LLu" -D USE_LOCAL_BITMAPS=%u",
		cmp_steps, (unsigned long long)bitmap_size_bits - 1, use_local);

	bitmap_size_bits *= cmp_steps;

	return kernel_params;
}

static int crypt_all(int *pcount, struct db_salt *salt)
{
	const int count = *pcount;
	static int zero;

	size_t *lws = local_work_size ? &local_work_size : NULL;

	global_work_size = local_work_size ? (count + local_work_size - 1) / local_work_size * local_work_size : count;

	//fprintf(stderr, "%s(%d) lws "Zu" gws "Zu" idx %u int_cand%d\n", __FUNCTION__, count, local_work_size, global_work_size, key_idx, mask_int_cand.num_int_cand);

	// copy keys to the device
	if (key_idx)
		HANDLE_CLERROR(clEnqueueWriteBuffer(queue[gpu_id], buffer_keys, CL_TRUE, 0, 4 * key_idx, saved_plain, 0, NULL, multi_profilingEvent[0]), "failed in clEnqueueWriteBuffer buffer_keys.");

	HANDLE_CLERROR(clEnqueueWriteBuffer(queue[gpu_id], buffer_idx, CL_TRUE, 0, 4 * global_work_size, saved_idx, 0, NULL, multi_profilingEvent[1]), "failed in clEnqueueWriteBuffer buffer_idx.");

	if (!is_static_gpu_mask)
		HANDLE_CLERROR(clEnqueueWriteBuffer(queue[gpu_id], buffer_int_key_loc, CL_TRUE, 0, 4 * global_work_size, saved_int_key_loc, 0, NULL, multi_profilingEvent[2]), "failed in clEnqueueWriteBuffer buffer_int_key_loc.");

	if (ocl_ver >= 120) {
		zero = 0;
		HANDLE_CLERROR(clEnqueueFillBuffer(queue[gpu_id], buffer_hash_ids, &zero, sizeof(cl_uint), 0, sizeof(cl_uint), 0, NULL, multi_profilingEvent[3]), "failed in clEnqueueFillBuffer buffer_hash_ids.");
		HANDLE_CLERROR(clEnqueueFillBuffer(queue[gpu_id], buffer_bitmap_dupe, &zero, sizeof(cl_uint), 0, sizeof(cl_uint) * (hash_table_size/32 + 1), 0, NULL, multi_profilingEvent[4]), "failed in clEnqueueFillBuffer buffer_bitmap_dupe.");
	}

	if (salt != NULL && salt->count > 100 &&
		(num_loaded_hashes - num_loaded_hashes / 10) > salt->count) {
		size_t old_ot_sz_bytes, old_ht_sz_bytes;
		prepare_table(salt);
		init_kernel(salt->count, select_bitmap(salt->count));

		HANDLE_CLERROR(clGetMemObjectInfo(buffer_offset_table, CL_MEM_SIZE, sizeof(size_t), &old_ot_sz_bytes, NULL), "failed to query buffer_offset_table.");

		if (old_ot_sz_bytes < offset_table_size *
			sizeof(OFFSET_TABLE_WORD)) {
			HANDLE_CLERROR(clReleaseMemObject(buffer_offset_table), "Error Releasing buffer_offset_table.");

			buffer_offset_table = clCreateBuffer(context[gpu_id], CL_MEM_READ_ONLY, offset_table_size * sizeof(OFFSET_TABLE_WORD), NULL, &ret_code);
			HANDLE_CLERROR(ret_code, "Error creating buffer argument buffer_offset_table.");
		}

		HANDLE_CLERROR(clGetMemObjectInfo(buffer_hash_table, CL_MEM_SIZE, sizeof(size_t), &old_ht_sz_bytes, NULL), "failed to query buffer_hash_table.");

		if (old_ht_sz_bytes < hash_table_size * sizeof(cl_uint) * 2) {
			HANDLE_CLERROR(clReleaseMemObject(buffer_hash_table), "Error Releasing buffer_hash_table.");
			HANDLE_CLERROR(clReleaseMemObject(buffer_bitmap_dupe), "Error Releasing buffer_bitmap_dupe.");

			buffer_bitmap_dupe = clCreateBuffer(context[gpu_id], CL_MEM_READ_WRITE, (hash_table_size/32 + 1) * sizeof(cl_uint), NULL, &ret_code);
			HANDLE_CLERROR(ret_code, "Error creating buffer argument buffer_bitmap_dupe.");
			buffer_hash_table = clCreateBuffer(context[gpu_id], CL_MEM_READ_ONLY, hash_table_size * sizeof(cl_uint) * 2, NULL, &ret_code);
			HANDLE_CLERROR(ret_code, "Error creating buffer argument buffer_hash_table.");
		}

		HANDLE_CLERROR(clEnqueueWriteBuffer(queue[gpu_id], buffer_bitmaps, CL_TRUE, 0, (bitmap_size_bits >> 3), bitmaps, 0, NULL, NULL), "failed in clEnqueueWriteBuffer buffer_bitmaps.");
		HANDLE_CLERROR(clEnqueueWriteBuffer(queue[gpu_id], buffer_offset_table, CL_TRUE, 0, sizeof(OFFSET_TABLE_WORD) * offset_table_size, offset_table, 0, NULL, NULL), "failed in clEnqueueWriteBuffer buffer_offset_table.");
		HANDLE_CLERROR(clEnqueueWriteBuffer(queue[gpu_id], buffer_hash_table, CL_TRUE, 0, sizeof(cl_uint) * hash_table_size * 2, hash_table_128, 0, NULL, NULL), "failed in clEnqueueWriteBuffer buffer_hash_table.");
		set_kernel_args();
	}

	HANDLE_CLERROR(clEnqueueNDRangeKernel(queue[gpu_id], crypt_kernel, 1, NULL, &global_work_size, lws, 0, NULL, multi_profilingEvent[5]), "failed in clEnqueueNDRangeKernel");

	HANDLE_CLERROR(clEnqueueReadBuffer(queue[gpu_id], buffer_hash_ids, CL_TRUE, 0, sizeof(cl_uint), hash_ids, 0, NULL, multi_profilingEvent[6]), "failed in reading back num cracked hashes.");

	if (hash_ids[0] > num_loaded_hashes) {
		fprintf(stderr, "Error, crypt_all kernel.\n");
		error();
	}

	if (hash_ids[0]) {
		HANDLE_CLERROR(clEnqueueReadBuffer(queue[gpu_id], buffer_return_hashes, CL_TRUE, 0, 2 * sizeof(cl_uint) * hash_ids[0], loaded_hashes, 0, NULL, multi_profilingEvent[7]), "failed in reading back return_hashes.");
		HANDLE_CLERROR(clEnqueueReadBuffer(queue[gpu_id], buffer_hash_ids, CL_TRUE, 0, (3 * hash_ids[0] + 1) * sizeof(cl_uint), hash_ids, 0, NULL, multi_profilingEvent[8]), "failed in reading data back hash_ids.");
	}

	*pcount *=  mask_int_cand.num_int_cand;
	return hash_ids[0];
}

static int cmp_all(void *binary, int count)
{
	if (count) return 1;
	return 0;
}

static int cmp_one(void *binary, int index)
{
	return (((unsigned int*)binary)[0] ==
		hash_table_128[hash_ids[3 + 3 * index]]);
}

static int cmp_exact(char *source, int index)
{
	unsigned int *t = (unsigned int *) get_binary(source);

	if (t[2] != loaded_hashes[2 * index])
		return 0;
	if (t[3] != loaded_hashes[2 * index + 1])
		return 0;
	return 1;
}

static void reset(struct db_main *db)
{
	if (db) {
		size_t buffer_size;
		if (ref_ctr > 0)
			release_clobj();

		buffer_size = db->format->params.max_keys_per_crypt;
		num_loaded_hashes = db->salts->count;
		prepare_table(db->salts);
		init_kernel(num_loaded_hashes, select_bitmap(num_loaded_hashes));
		create_clobj(buffer_size, NULL);
		HANDLE_CLERROR(clEnqueueWriteBuffer(queue[gpu_id], buffer_bitmaps, CL_TRUE, 0, (size_t)(bitmap_size_bits >> 3), bitmaps, 0, NULL, NULL), "failed in clEnqueueWriteBuffer buffer_bitmaps.");
		HANDLE_CLERROR(clEnqueueWriteBuffer(queue[gpu_id], buffer_offset_table, CL_TRUE, 0, sizeof(OFFSET_TABLE_WORD) * offset_table_size, offset_table, 0, NULL, NULL), "failed in clEnqueueWriteBuffer buffer_offset_table.");
		HANDLE_CLERROR(clEnqueueWriteBuffer(queue[gpu_id], buffer_hash_table, CL_TRUE, 0, sizeof(cl_uint) * hash_table_size * 2, hash_table_128, 0, NULL, NULL), "failed in clEnqueueWriteBuffer buffer_hash_table.");
	}
	else {
		unsigned int *binary, i = 0;
		char *ciphertext;
		size_t gws_limit;
		unsigned int flag;

		opencl_get_user_preferences(FORMAT_LABEL);
		flag = (options.flags & FLG_MASK_CHK) && !global_work_size;

		gws_limit = MIN((0xf << 22) * 4 / BUFSIZE,
		                get_max_mem_alloc_size(gpu_id) / BUFSIZE);

		while (tests[num_loaded_hashes].ciphertext != NULL)
			num_loaded_hashes++;

		loaded_hashes = (cl_uint*)mem_alloc(16 * num_loaded_hashes);

		while (tests[i].ciphertext != NULL) {
			ciphertext = split(tests[i].ciphertext, 0, &FMT_STRUCT);
			binary = (unsigned int*)get_binary(ciphertext);
			loaded_hashes[4 * i] = binary[0];
			loaded_hashes[4 * i + 1] = binary[1];
			loaded_hashes[4 * i + 2] = binary[2];
			loaded_hashes[4 * i + 3] = binary[3];
			i++;
		}

		num_loaded_hashes = create_perfect_hash_table(128, (void *)loaded_hashes,
				num_loaded_hashes,
			        &offset_table,
			        &offset_table_size,
			        &hash_table_size, 0);

		if (!num_loaded_hashes) {
			MEM_FREE(hash_table_128);
			MEM_FREE(offset_table);
			fprintf(stderr, "Failed to create Hash Table for self test.\n");
			error();
		}

		hash_ids = (cl_uint*)mem_alloc((3 * num_loaded_hashes + 1) * sizeof(cl_uint));

		init_kernel(num_loaded_hashes, select_bitmap(num_loaded_hashes));

		// Initialize openCL tuning (library) for this format.
		opencl_init_auto_setup(SEED, 0, NULL, warn, 1, self,
		                       create_clobj, release_clobj,
		                       2 * BUFSIZE, gws_limit);

		//Auto tune execution from shared/included code.
		autotune_run(self, 1, gws_limit,
		             (cpu(device_info[gpu_id]) ?
		              500000000ULL : 1000000000ULL));

		if (options.flags & FLG_MASK_CHK) {
			fprintf(stdout, "Using Mask Mode with internal "
			        "candidate generation%s", flag ? "" : "\n");
			if (flag) {
				self->params.max_keys_per_crypt /= 64;
				fprintf(stdout,
				        ", global worksize(GWS) set to %d\n",
				        self->params.max_keys_per_crypt);
			}
		}
		HANDLE_CLERROR(clEnqueueWriteBuffer(queue[gpu_id], buffer_bitmaps, CL_TRUE, 0, (bitmap_size_bits >> 3), bitmaps, 0, NULL, NULL), "failed in clEnqueueWriteBuffer buffer_bitmaps.");
		HANDLE_CLERROR(clEnqueueWriteBuffer(queue[gpu_id], buffer_offset_table, CL_TRUE, 0, sizeof(OFFSET_TABLE_WORD) * offset_table_size, offset_table, 0, NULL, NULL), "failed in clEnqueueWriteBuffer buffer_offset_table.");
		HANDLE_CLERROR(clEnqueueWriteBuffer(queue[gpu_id], buffer_hash_table, CL_TRUE, 0, sizeof(cl_uint) * hash_table_size * 2, hash_table_128, 0, NULL, NULL), "failed in clEnqueueWriteBuffer buffer_hash_table.");
		hash_ids[0] = 0;
	}
}

struct fmt_main FMT_STRUCT = {
	{
		FORMAT_LABEL,
		FORMAT_NAME,
		ALGORITHM_NAME,
		BENCHMARK_COMMENT,
		BENCHMARK_LENGTH,
		0,
		PLAINTEXT_LENGTH,
		BINARY_SIZE,
		BINARY_ALIGN,
		SALT_SIZE,
		SALT_ALIGN,
		MIN_KEYS_PER_CRYPT,
		MAX_KEYS_PER_CRYPT,
		FMT_CASE | FMT_8_BIT,
#if FMT_MAIN_VERSION > 11
		{ NULL },
#endif
		tests
	}, {
		init,
		done,
		reset,
		fmt_default_prepare,
		valid,
		split,
		get_binary,
		fmt_default_salt,
#if FMT_MAIN_VERSION > 11
		{ NULL },
#endif
		fmt_default_source,
		{
			fmt_default_binary_hash_0,
			fmt_default_binary_hash_1,
			fmt_default_binary_hash_2,
			fmt_default_binary_hash_3,
			fmt_default_binary_hash_4,
			fmt_default_binary_hash_5,
			fmt_default_binary_hash_6
		},
		fmt_default_salt_hash,
		NULL,
		fmt_default_set_salt,
		set_key,
		get_key,
		clear_keys,
		crypt_all,
		{
			get_hash_0,
			get_hash_1,
			get_hash_2,
			get_hash_3,
			get_hash_4,
			get_hash_5,
			get_hash_6
		},
		cmp_all,
		cmp_one,
		cmp_exact
	}
};

#endif /* plugin stanza */

#endif /* HAVE_OPENCL */
