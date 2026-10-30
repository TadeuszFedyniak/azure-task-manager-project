variable "subscription_id" {
  description = "Azure subscription ID (az account show --query id -o tsv)"
  type        = string
}
variable "location" {
  type    = string
  default = "polandcentral"
}
variable "project_name" {
  type    = string
  default = "taskmanagerdemo"
}
variable "admin_username" {
  type    = string
  default = "azureadmin"
}
variable "ssh_public_key_path" {
  description = "Local path to the SSH public key, e.g. ~/.ssh/id_ed25519.pub"
  type        = string
}
variable "allowed_ssh_cidr" {
  description = "Your public IP in CIDR notation, e.g. 203.0.113.10/32. Do not use 0.0.0.0/0."
  type        = string
}
