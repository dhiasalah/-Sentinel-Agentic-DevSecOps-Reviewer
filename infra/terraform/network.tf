resource "oci_core_vcn" "sentinel" {
  compartment_id = var.compartment_ocid
  cidr_blocks    = ["10.0.0.0/16"]
  display_name   = "sentinel-vcn"
  dns_label      = "sentinel"
}

resource "oci_core_internet_gateway" "gate" {
  compartment_id = var.compartment_ocid
  vcn_id         = oci_core_vcn.sentinel.id
  display_name   = "sentinel-igw"
  enabled        = true
}

resource "oci_core_route_table" "public" {
  compartment_id = var.compartment_ocid
  vcn_id         = oci_core_vcn.sentinel.id
  display_name   = "sentinel-public-rt"

  route_rules {
    destination       = "0.0.0.0/0"
    destination_type  = "CIDR_BLOCK"
    network_entity_id = oci_core_internet_gateway.gate.id
  }
}

resource "oci_core_security_list" "public" {
  compartment_id = var.compartment_ocid
  vcn_id         = oci_core_vcn.sentinel.id
  display_name   = "sentinel-public-sl"

  # Going OUT: the server may call anything (GitHub, Supabase, the LLM APIs, package updates)
  egress_security_rules {
    destination = "0.0.0.0/0"
    protocol    = "all"
  }

  # Coming IN: SSH only from your own IP
  ingress_security_rules {
    description = "SSH from my IP only"
    source      = var.ssh_allowed_cidr
    protocol    = "6" # 6 = TCP
    tcp_options {
      min = 22
      max = 22
    }
  }

  # Coming IN: web traffic from anyone
  ingress_security_rules {
    description = "HTTP"
    source      = "0.0.0.0/0"
    protocol    = "6"
    tcp_options {
      min = 80
      max = 80
    }
  }

  ingress_security_rules {
    description = "HTTPS"
    source      = "0.0.0.0/0"
    protocol    = "6"
    tcp_options {
      min = 443
      max = 443
    }
  }

  # Coming IN: one small network-health message ("your packet is too big"); without it some downloads hang
  ingress_security_rules {
    description = "ICMP path MTU discovery"
    source      = "0.0.0.0/0"
    protocol    = "1" # 1 = ICMP
    icmp_options {
      type = 3
      code = 4
    }
  }
}

# Oracle gives every VCN a default security list with SSH open to the whole internet.
# Taking it over with no rules empties it, so nothing can use it by mistake.
resource "oci_core_default_security_list" "unused" {
  manage_default_resource_id = oci_core_vcn.sentinel.default_security_list_id
  display_name               = "sentinel-default-sl-empty"
}

resource "oci_core_subnet" "public" {
  compartment_id             = var.compartment_ocid
  vcn_id                     = oci_core_vcn.sentinel.id
  cidr_block                 = "10.0.1.0/24"
  display_name               = "sentinel-public-subnet"
  dns_label                  = "public"
  route_table_id             = oci_core_route_table.public.id
  security_list_ids          = [oci_core_security_list.public.id]
  prohibit_public_ip_on_vnic = false
}
